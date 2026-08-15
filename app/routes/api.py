import os
import glob
import json
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
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
        "model_provider": req.model_provider,  # wire API override through graph
        "model_name": req.model_name,
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        logger.info(f"[API: /api/query] Invoking LangGraph workflow for thread '{thread_id}'...")
        final_state = legal_graph.invoke(initial_state, config=config)

        markdown_out = final_state.get("final_markdown_output") or final_state.get("draft_opinion") or "No output generated."
        
        # Save assistant message
        save_message(thread_id, role="assistant", content=markdown_out, metadata={
            "risk_flags": final_state.get("compliance_risk_flags", []),
            "reasoning_plan": final_state.get("reasoning_plan", [])
        })
        
        return {
            "thread_id": thread_id,
            "markdown_output": markdown_out,
            "requires_user_clarification": final_state.get("requires_user_clarification", False),
            "clarification_prompt": final_state.get("clarification_prompt"),
            "compliance_risk_flags": final_state.get("compliance_risk_flags", []),
            "reasoning_plan": final_state.get("reasoning_plan", []),
            "critic_verified": final_state.get("critic_verified", True)
        }
    except Exception as e:
        logger.error(f"Error processing legal query graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    
    try:
        logger.info(f"[API: /api/analyze-application] Invoking LangGraph evaluation graph...")
        final_state = legal_graph.invoke(initial_state, config=config)
        markdown_out = final_state.get("final_markdown_output") or "Analysis completed."
        
        save_message(thread_id, role="assistant", content=markdown_out, metadata={
            "risk_flags": final_state.get("compliance_risk_flags", [])
        })
        
        return {
            "thread_id": thread_id,
            "markdown_output": markdown_out,
            "compliance_risk_flags": final_state.get("compliance_risk_flags", []),
            "reasoning_plan": final_state.get("reasoning_plan", []),
            "parsed_form": form_dict
        }
    except Exception as e:
        logger.error(f"Error analyzing building application: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-pdf")
async def upload_permit_pdf(file: UploadFile = File(...), thread_id: str = Form("default_session")):
    logger.info(f"[API: /api/upload-pdf] Received PDF file '{file.filename}' for thread '{thread_id}'")
    try:
        file_bytes = await file.read()
        parsed_doc = parse_pdf_document(file_bytes, file.filename)
        extracted_form = parse_form_b7_from_text_or_json(parsed_doc["full_text"])
        logger.info(f"[API: /api/upload-pdf] Extracted fields: project='{extracted_form.get('project_name')}', area={extracted_form.get('project_area_sqm')}")
        
        # Invoke graph with extracted fields
        form_obj = FormB7Application(**extracted_form)
        analysis_req = ApplicationAnalysisRequest(form_data=form_obj, thread_id=thread_id)
        return await analyze_building_application(analysis_req)
    except Exception as e:
        logger.error(f"Failed to process uploaded PDF: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to process uploaded PDF: {str(e)}")



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
