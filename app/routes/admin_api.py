import os
import json
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.services.document_loader import load_mock_corpus_documents
from app.services.hybrid_retriever import hybrid_retriever
from app.db import register_corpus_document, get_all_registered_documents

logger = logging.getLogger(__name__)
admin_router = APIRouter(prefix="/api/admin", tags=["Admin KB APIs"])

MOCK_CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "mock_corpus")

@admin_router.post("/corpus/upload")
async def upload_admin_knowledge_document(
    doc_id: str = Form(...),
    document_name: str = Form(...),
    doc_type: str = Form(...), # Rules | Government Order | Circular | Judgment
    issuing_authority: str = Form(""),
    doc_date: str = Form(""),
    file: UploadFile = File(...)
):
    try:
        content_bytes = await file.read()
        text_content = content_bytes.decode("utf-8", errors="ignore")
        
        doc_json = {
            "doc_id": doc_id,
            "document_name": document_name,
            "doc_type": doc_type,
            "issuing_authority": issuing_authority,
            "date": doc_date,
            "is_outdated": False,
            "superseded_by": None,
            "download_url": f"/api/documents/download/{doc_id}",
            "sections": [
                {
                    "section_number": "Main Content",
                    "heading": document_name,
                    "page_number": 1,
                    "content": text_content
                }
            ]
        }
        
        save_path = os.path.join(MOCK_CORPUS_DIR, f"{doc_id}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(doc_json, f, indent=2)
            
        register_corpus_document(doc_json)
        
        # Trigger Reindex
        chunks = load_mock_corpus_documents()
        hybrid_retriever.index_documents(chunks)
        
        return {
            "message": f"Successfully uploaded and indexed '{document_name}' into Knowledge Base.",
            "doc_id": doc_id,
            "total_chunks_indexed": len(chunks)
        }
    except Exception as e:
        logger.error(f"Error in admin document upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/corpus/reindex")
async def reindex_knowledge_base():
    try:
        chunks = load_mock_corpus_documents()
        hybrid_retriever.index_documents(chunks)
        return {
            "message": "Knowledge base re-indexed successfully out-of-the-box.",
            "total_chunks": len(chunks),
            "documents": get_all_registered_documents()
        }
    except Exception as e:
        logger.error(f"Re-indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
