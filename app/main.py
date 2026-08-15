import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.services.document_loader import load_mock_corpus_documents
from app.services.hybrid_retriever import hybrid_retriever
from app.routes.api import router as officer_router
from app.routes.admin_api import admin_router as admin_api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing SQLite Database...")
    init_db()
    
    logger.info("Auto-populating and indexing 6 Mock Legal Corpus documents...")
    chunks = load_mock_corpus_documents()
    hybrid_retriever.index_documents(chunks)
    logger.info(f"Knowledge Base ready with {len(chunks)} statutory chunks.")

    # LLM connectivity health check — runs at startup to surface config problems early
    logger.info("Running LLM connectivity health check...")
    from app.models.llm_factory import check_llm_health
    llm_health = check_llm_health()
    if llm_health["status"] == "ok":
        logger.info(
            f"✅ LLM Health Check PASSED — provider={llm_health['provider']}, "
            f"model={llm_health['model']}. System is fully operational."
        )
    else:
        logger.critical(
            f"❌ LLM Health Check FAILED — provider={llm_health['provider']}, "
            f"model={llm_health['model']}. "
            f"Reason: {llm_health['message']} "
            "The system will NOT return hardcoded responses — queries will fail with a clear error "
            "until the LLM is properly configured. "
            "ACTION REQUIRED: Check your .env file (GROQ_API_KEY / OPENAI_API_KEY / LLM_PROVIDER) "
            "and verify the API key is valid. Call GET /api/health for real-time status."
        )
    
    yield
    logger.info("Shutting down Government Legal Intelligence Assistant.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="AI Copilot for Law Department & LSGD legal officers evaluating building permit compliance.",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(officer_router)
app.include_router(admin_api_router)

# Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": f"Welcome to {settings.APP_NAME} v{settings.VERSION}"}
