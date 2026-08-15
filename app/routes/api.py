import os
import glob
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from app.models.schemas import LegalQueryRequest, ApplicationAnalysisRequest, FormB7Application
from app.graph.workflow import legal_graph
from app.db import (
    save_message,
    get_sliding_window_messages,
    get_all_registered_documents,
    get_db_connection,
    get_all_threads
)
from app.services.pdf_parser import parse_pdf_document, parse_form_b7_from_text_or_json
from app.models.llm_factory import check_llm_health
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Officer APIs"])

MOCK_CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "mock_corpus")

@router.post("/query")
async def process_legal_query(req: LegalQueryRequest):
    thread_id = req.thread_id or "default_session"
    logger.info(f"[API: /api/query] Received query for thread '{thread_id}': '{req.query[:60]}...'")
    
    # Check sliding window history from SQLite
    history_msgs = get_sliding_window_messages(thread_id, limit=settings.SLIDING_WINDOW_SIZE)
    
    # Save incoming user message
    save_message(thread_id, role="user", content=req.query)
    
    initial_state = {
        "thread_id": thread_id,
        "raw_input": req.query,
        "input_type": "clarification_answer" if req.is_clarification_response else "legal_query",
        "parsed_form": {},
        "chat_history": history_msgs,
        "iteration_count": 0,
        "model_provider": req.model_provider,
        "model_name": req.model_name,
        "document_context": req.document_context or None,
        "document_filename": req.document_filename or None,
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    
    async def event_generator():
        try:
            logger.info(f"[API: /api/query] Invoking LangGraph streaming workflow for thread '{thread_id}'...")
            final_output = ""
            risk_flags = []
            
            async for event in legal_graph.astream(initial_state, config=config, stream_mode="updates"):
                for node, update in event.items():
                    if update is None:
                        continue
                        
                    # Stream which node just finished
                    yield f"data: {json.dumps({'type': 'node_status', 'node': node})}\n\n"
                    
                    if node == "planner":
                        if update.get("reasoning_plan"):
                            yield f"data: {json.dumps({'type': 'plan', 'content': update['reasoning_plan']})}\n\n"
                        if update.get("requires_user_clarification"):
                            yield f"data: {json.dumps({'type': 'clarification', 'content': update['clarification_prompt']})}\n\n"
                    
                    if node == "multi_agent_eval":
                        if update.get("compliance_risk_flags"):
                            risk_flags = update["compliance_risk_flags"]
                            yield f"data: {json.dumps({'type': 'flags', 'content': risk_flags})}\n\n"
                            
                    if node == "synthesis" or node == "chitchat":
                        final_output = update.get("final_markdown_output") or update.get("draft_opinion") or "No output generated."
                        # Smooth pseudo-streaming for final text
                        import re
                        tokens = re.split(r'(\s+)', final_output)
                        for token in tokens:
                            if token:
                                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                await asyncio.sleep(0.01)
                                
                        # Emit structured sources at the end so they appear after text
                        structured_sources = update.get("sources_used", [])
                        if structured_sources:
                            yield f"data: {json.dumps({'type': 'sources', 'content': structured_sources})}\n\n"
                                
            # End of stream, save to DB
            save_message(thread_id, role="assistant", content=final_output, metadata={"risk_flags": risk_flags})
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Error processing legal query graph stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    headers = {
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache",
        "Transfer-Encoding": "chunked",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.post("/analyze-application")
async def analyze_building_application(req: ApplicationAnalysisRequest):
    thread_id = req.thread_id or "default_session"
    form_dict = req.form_data.model_dump()
    logger.info(f"[API: /api/analyze-application] Received Form B-7 review request for project '{form_dict.get('project_name')}' ({form_dict.get('project_area_sqm')} sq.m)")
    
    query_text = (
        f"Building permit application Form B-7 review for project '{form_dict.get('project_name')}', "
        f"location: '{form_dict.get('location')}', area: {form_dict.get('project_area_sqm')} sq.m., "
        f"environmental clearance status: {form_dict.get('environmental_clearance_status')}, "
        f"NOC status: {form_dict.get('local_body_noc_status')}."
    )
    
    save_message(thread_id, role="user", content=query_text)
    
    initial_state = {
        "thread_id": thread_id,
        "raw_input": query_text,
        "input_type": "form_b7",
        "parsed_form": form_dict,
        "chat_history": get_sliding_window_messages(thread_id),
        "iteration_count": 0,
        "model_provider": req.model_provider,  # wire API override through graph
        "model_name": req.model_name,
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    
    async def event_generator():
        try:
            logger.info(f"[API: /api/analyze-application] Invoking LangGraph streaming evaluation graph...")
            final_output = ""
            risk_flags = []
            
            async for event in legal_graph.astream(initial_state, config=config, stream_mode="updates"):
                for node, update in event.items():
                    if update is None:
                        continue
                        
                    # Stream which node just finished
                    yield f"data: {json.dumps({'type': 'node_status', 'node': node})}\n\n"

                    if node == "planner":
                        if update.get("reasoning_plan"):
                            yield f"data: {json.dumps({'type': 'plan', 'content': update['reasoning_plan']})}\n\n"
                    
                    if node == "multi_agent_eval":
                        if update.get("compliance_risk_flags"):
                            risk_flags = update["compliance_risk_flags"]
                            yield f"data: {json.dumps({'type': 'flags', 'content': risk_flags})}\n\n"
                            
                    if node == "synthesis":
                        final_output = update.get("final_markdown_output") or "Analysis completed."
                        import re
                        tokens = re.split(r'(\s+)', final_output)
                        for token in tokens:
                            if token:
                                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                await asyncio.sleep(0.01)
                                
                        structured_sources = update.get("sources_used", [])
                        if structured_sources:
                            yield f"data: {json.dumps({'type': 'sources', 'content': structured_sources})}\n\n"
                                
            save_message(thread_id, role="assistant", content=final_output, metadata={"risk_flags": risk_flags})
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"Error analyzing building application stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    headers = {
        "X-Accel-Buffering": "no",
        "Cache-Control": "no-cache",
        "Transfer-Encoding": "chunked",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.post("/upload-pdf")
async def upload_permit_pdf(file: UploadFile = File(...), thread_id: str = Form("default_session")):
    """Approach B: Extract raw text from any PDF and return it so the frontend
    can attach it as document_context to the next user query."""
    logger.info(f"[API: /api/upload-pdf] Extracting text from '{file.filename}' for thread '{thread_id}'")
    try:
        file_bytes = await file.read()
        parsed_doc = parse_pdf_document(file_bytes, file.filename)
        extracted_text = parsed_doc.get("full_text", "").strip()
        word_count = len(extracted_text.split())
        page_count = len(parsed_doc.get("pages", [])) or 1
        logger.info(f"[API: /api/upload-pdf] Extracted {word_count} words / {page_count} pages from '{file.filename}'")
        return JSONResponse(content={
            "success": True,
            "filename": file.filename,
            "extracted_text": extracted_text,
            "word_count": word_count,
            "page_count": page_count,
        })
    except Exception as e:
        logger.error(f"Failed to extract text from uploaded PDF: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")



@router.get("/documents/download/{doc_id}")
async def download_mock_document(doc_id: str):
    # Check for PDF file match first
    pdf_files = glob.glob(os.path.join(MOCK_CORPUS_DIR, "*.pdf"))
    for pdf_path in pdf_files:
        fn_lower = os.path.basename(pdf_path).lower()
        if doc_id.lower() in fn_lower or ("building_rules" in doc_id and "building_rules" in fn_lower) or ("45_2024" in doc_id and "45_2024" in fn_lower) or ("22_2021" in doc_id and "22_2021" in fn_lower) or ("12_2025" in doc_id and "12_2025" in fn_lower) or ("1234_2023" in doc_id and "1234_2023" in fn_lower) or ("form_b7" in doc_id and "form_b7" in fn_lower):
            return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))
            
    json_path = os.path.join(MOCK_CORPUS_DIR, f"{doc_id}.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)

    raise HTTPException(status_code=404, detail="Requested legal document not found.")



@router.get("/documents")
async def list_corpus_documents():
    return get_all_registered_documents()


@router.get("/threads")
async def list_threads():
    return get_all_threads()


@router.get("/threads/{thread_id}")
async def get_thread_history(thread_id: str):
    msgs = get_sliding_window_messages(thread_id, limit=20)
    return {"thread_id": thread_id, "messages": msgs}


@router.get("/models")
async def get_available_models():
    return {
        "current_provider": settings.LLM_PROVIDER,
        "current_model": settings.GROQ_MODEL_NAME if settings.LLM_PROVIDER == "groq" else settings.OPENAI_MODEL_NAME,
        "supported_providers": ["groq", "openai", "ollama"],
        "groq_models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "openai_models": ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    }


@router.get("/health")
async def health_check():
    """
    Checks LLM provider connectivity and knowledge base status.
    Returns a structured health report — useful for diagnosing hardcoded/silent-failure issues.
    """
    from app.services.hybrid_retriever import hybrid_retriever
    from app.db import get_all_registered_documents

    llm_health = check_llm_health()
    kb_docs = get_all_registered_documents()
    kb_indexed = hybrid_retriever._is_indexed

    overall_status = "ok" if (llm_health["status"] == "ok" and kb_indexed) else "degraded"

    return {
        "overall_status": overall_status,
        "llm": llm_health,
        "knowledge_base": {
            "status": "indexed" if kb_indexed else "not_indexed",
            "document_count": len(kb_docs),
            "documents": [{"doc_id": d["doc_id"], "name": d["document_name"], "type": d["doc_type"]} for d in kb_docs],
        },
        "app_version": settings.VERSION,
    }
