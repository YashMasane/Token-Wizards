import os
import glob
import json
import re
import logging
from typing import List, Dict, Any
from app.db import register_corpus_document
from app.services.pdf_parser import parse_pdf_document

logger = logging.getLogger(__name__)

MOCK_CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "mock_corpus")

def classify_pdf_metadata(filename: str, text: str) -> Dict[str, Any]:
    """
    Classifies doc_type, document_name, date, and supersession state from PDF filename & text.
    Strips parenthetical suffixes like '(1)' from filenames before matching.
    Logs a WARNING if the file cannot be classified (instead of silently defaulting).
    """
    # Normalise: strip parenthetical suffixes e.g. 'doc (1).pdf' -> 'doc.pdf'
    clean_name = re.sub(r'\s*\(\d+\)', '', filename)
    fn_lower = clean_name.lower()
    base_name = os.path.splitext(clean_name)[0]

    meta = {
        "doc_id": base_name,
        "document_name": base_name.replace('_', ' ').title(),
        "doc_type": "Rules",
        "issuing_authority": "Government of Kerala",
        "date": "2024-01-01",
        "is_outdated": False,
        "superseded_by": None,
        "download_url": f"/api/documents/download/{base_name}"
    }

    if "building_rules" in fn_lower or "rules_2022" in fn_lower:
        meta["doc_id"] = "doc1_kerala_building_rules_2022"
        meta["document_name"] = "Kerala Building Rules, 2022"
        meta["doc_type"] = "Rules"
        meta["issuing_authority"] = "Local Self Government Department"
        meta["date"] = "2022-01-15"
    elif "45_2024" in fn_lower or "45/2024" in fn_lower:
        meta["doc_id"] = "doc2_go_p_45_2024_lsgd"
        meta["document_name"] = "GO(P) No. 45/2024/LSGD"
        meta["doc_type"] = "Government Order"
        meta["issuing_authority"] = "Local Self Government Department"
        meta["date"] = "2024-04-10"
    elif "22_2021" in fn_lower or "22/2021" in fn_lower:
        meta["doc_id"] = "doc3_go_22_2021_lsgd"
        meta["document_name"] = "GO No. 22/2021/LSGD"
        meta["doc_type"] = "Government Order"
        meta["is_outdated"] = True
        meta["superseded_by"] = "GO(P) No. 45/2024/LSGD"
        meta["issuing_authority"] = "Local Self Government Department"
        meta["date"] = "2021-03-15"
    elif "12_2025" in fn_lower or "circular" in fn_lower:
        meta["doc_id"] = "doc4_circular_12_2025_env"
        meta["document_name"] = "Circular No. 12/2025/Env"
        meta["doc_type"] = "Circular"
        meta["issuing_authority"] = "Environment Department"
        meta["date"] = "2025-01-20"
    elif "1234_2023" in fn_lower or "judgment" in fn_lower or "wp_c" in fn_lower:
        meta["doc_id"] = "doc5_judgment_hc_1234_2023"
        meta["document_name"] = "High Court of Kerala, WP(C) No. 1234/2023"
        meta["doc_type"] = "Judgment"
        meta["issuing_authority"] = "High Court of Kerala"
        meta["date"] = "2023-11-05"
    elif "form_b7" in fn_lower or "application" in fn_lower:
        meta["doc_id"] = "sample_form_b7"
        meta["document_name"] = "Building Permit Application Form B-7"
        meta["doc_type"] = "Application"
    else:
        logger.warning(
            f"[DocumentLoader] PDF '{filename}' could not be classified by filename pattern. "
            f"Defaulting doc_type='Rules' and doc_id='{meta['doc_id']}'. "
            "Consider renaming the file to include a recognisable keyword "
            "(e.g. 'building_rules', '45_2024', 'judgment', 'circular')."
        )

    meta["download_url"] = f"/api/documents/download/{meta['doc_id']}"
    return meta

def load_mock_corpus_documents(skip_db: bool = False) -> List[Dict[str, Any]]:
    """
    Loads statutory documents directly from PDF files in data/mock_corpus/ using pdfplumber.
    Falls back to JSON documents if PDFs are not present.
    """
    pdf_files = glob.glob(os.path.join(MOCK_CORPUS_DIR, "*.pdf"))
    documents = []

    if pdf_files:
        logger.info(f"Loading {len(pdf_files)} PDF documents from {MOCK_CORPUS_DIR} using pdfplumber...")
        for pdf_path in pdf_files:
            try:
                filename = os.path.basename(pdf_path)
                with open(pdf_path, "rb") as f:
                    file_bytes = f.read()

                parsed_pdf = parse_pdf_document(file_bytes, filename)
                meta = classify_pdf_metadata(filename, parsed_pdf["full_text"])

                # Skip application form from legal vector database
                if meta["doc_type"] == "Application" or meta["doc_id"] == "sample_form_b7":
                    if not skip_db:
                        register_corpus_document(meta)
                    continue

                register_corpus_document(meta)

                # Chunk pages into statutory chunks with section clause extraction
                for page_obj in parsed_pdf["pages"]:
                    page_num = page_obj["page_number"]
                    page_text = page_obj["text"]
                    tables = page_obj.get("tables", [])

                    # Detect Section/Rule/Para headers in page text
                    clauses = re.findall(r"(Section\s*\d+(?:\(\d+\))?|Para\s*\d+|Key\s*Holding|Case\s*Details)", page_text, re.IGNORECASE)
                    clause_str = ", ".join(list(set(clauses))) if clauses else f"Page {page_num}"

                    content_full = page_text
                    if tables:
                        content_full += "\n\n### Extracted Tables:\n" + "\n\n".join(tables)

                    chunk_payload = {
                        "chunk_id": f"{meta['doc_id']}_p{page_num}",
                        "doc_id": meta["doc_id"],
                        "document_name": meta["document_name"],
                        "doc_type": meta["doc_type"],
                        "issuing_authority": meta["issuing_authority"],
                        "doc_date": meta["date"],
                        "is_outdated": meta["is_outdated"],
                        "superseded_by": meta["superseded_by"],
                        "page_number": page_num,
                        "heading": f"{meta['document_name']} (Page {page_num})",
                        "clause_or_rule": clause_str,
                        "content": content_full,
                        "download_url": meta["download_url"]
                    }
                    documents.append(chunk_payload)

            except Exception as e:
                logger.error(f"Error extracting PDF corpus file {pdf_path}: {e}")

        logger.info(f"Loaded {len(documents)} PDF statutory chunks from {len(pdf_files)} PDF files.")
        return documents

    # Fallback to JSON files if no PDFs
    json_files = glob.glob(os.path.join(MOCK_CORPUS_DIR, "*.json"))
    logger.info(f"Loading {len(json_files)} JSON mock documents...")
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                doc_data = json.load(f)

            if doc_data.get("doc_type") == "Application" or doc_data.get("doc_id") == "sample_form_b7":
                if not skip_db:
                    register_corpus_document(doc_data)
                continue

            if not skip_db:
                register_corpus_document(doc_data)
            doc_id = doc_data["doc_id"]
            
            for sec in doc_data.get("sections", []):
                chunk_id = f"{doc_id}_{sec.get('section_number', '').replace(' ', '_')}"
                documents.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "document_name": doc_data["document_name"],
                    "doc_type": doc_data["doc_type"],
                    "issuing_authority": doc_data.get("issuing_authority", ""),
                    "doc_date": doc_data.get("date", ""),
                    "is_outdated": doc_data.get("is_outdated", False),
                    "superseded_by": doc_data.get("superseded_by"),
                    "page_number": sec.get("page_number", 1),
                    "heading": sec.get("heading", ""),
                    "clause_or_rule": sec.get("section_number", ""),
                    "content": sec.get("content", ""),
                    "download_url": doc_data.get("download_url", f"/api/documents/download/{doc_id}")
                })
        except Exception as e:
            logger.error(f"Error loading JSON corpus file {jf}: {e}")

    return documents
