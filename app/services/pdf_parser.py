import re
import io
import logging
from typing import Dict, Any, List, Optional
import pdfplumber
from pypdf import PdfReader
import json

logger = logging.getLogger(__name__)

def parse_pdf_document(file_bytes: bytes, filename: str = "uploaded_doc.pdf") -> Dict[str, Any]:
    """
    Extracts text, headings, page numbers, and markdown tables from a PDF using pdfplumber.
    Returns structured document representation.
    """
    pages_data = []
    full_text_builder = []
    tables_found = []

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                page_text = page.extract_text() or ""
                full_text_builder.append(page_text)
                
                # Table Extraction
                tables = page.extract_tables()
                extracted_tables = []
                for table in tables:
                    if not table:
                        continue
                    # Convert to Markdown table
                    header = table[0]
                    rows = table[1:]
                    md_table = ""
                    if header:
                        header_clean = [str(cell or "").replace("\n", " ") for cell in header]
                        md_table += "| " + " | ".join(header_clean) + " |\n"
                        md_table += "| " + " | ".join(["---"] * len(header_clean)) + " |\n"
                        for row in rows:
                            row_clean = [str(cell or "").replace("\n", " ") for cell in row]
                            md_table += "| " + " | ".join(row_clean) + " |\n"
                    extracted_tables.append(md_table)
                    tables_found.append({"page": page_num, "table_md": md_table})
                
                pages_data.append({
                    "page_number": page_num,
                    "text": page_text,
                    "tables": extracted_tables
                })
    except Exception as e:
        logger.error(f"pdfplumber extraction failed for {filename}: {e}. Fallback to pypdf.")
        # Fallback to PyPDF
        reader = PdfReader(io.BytesIO(file_bytes))
        for page_idx, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            full_text_builder.append(page_text)
            pages_data.append({
                "page_number": page_idx + 1,
                "text": page_text,
                "tables": []
            })

    full_text = "\n\n".join(full_text_builder)
    return {
        "filename": filename,
        "full_text": full_text,
        "pages": pages_data,
        "tables": tables_found
    }


def parse_form_b7_from_text_or_json(raw_input: str, provider: str = None) -> Dict[str, Any]:
    """
    Extracts Form B-7 fields from PDF raw text or text input using LLM structured extraction with regex fallback.
    """
    logger.info(f"[PDFParser] Parsing Form B-7 parameters from input length: {len(raw_input)}")
    
    # Try LLM Structured Extraction first
    try:
        from app.models.llm_factory import get_llm
        llm = get_llm(provider=provider, temperature=0.0)
        prompt = f"""Extract the following Form B-7 application fields from this document text:
1. project_name (string)
2. location (string, include distance to water body if present)
3. project_area_sqm (number)
4. environmental_clearance_status ("Yes" or "No")
5. local_body_noc_status ("Yes" or "No")
6. applicant_declaration (string)
7. cited_orders (array of strings)

DOCUMENT TEXT:
{raw_input[:3000]}

Return ONLY valid JSON matching this schema:
{{
  "project_name": "...",
  "location": "...",
  "project_area_sqm": 5000,
  "environmental_clearance_status": "No",
  "local_body_noc_status": "Yes",
  "applicant_declaration": "All mandatory approvals are in place",
  "cited_orders": ["GO No. 22/2021/LSGD"]
}}
"""
        res = llm.invoke([{"role": "user", "content": prompt}])
        content = res.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
        
        parsed_json = json.loads(content)
        if parsed_json.get("project_area_sqm") and parsed_json.get("project_name"):
            logger.info(f"[PDFParser] LLM structured extraction successful: {parsed_json.get('project_name')} ({parsed_json.get('project_area_sqm')} sq.m)")
            return parsed_json
    except Exception as e:
        logger.warning(f"[PDFParser] LLM structured extraction failed or offline ({e}). Using regex rules fallback.")

    # Regex Fallback Engine — returns None for fields that cannot be extracted
    # so the Planner clarification logic can ask the user instead of inventing data
    fields = {
        "project_name": None,
        "location": None,
        "project_area_sqm": None,
        "environmental_clearance_status": None,
        "local_body_noc_status": None,
        "applicant_declaration": None,
        "cited_orders": []
    }
    
    proj_match = re.search(r"Project\s*(?:name|title)?[:\-]\s*([^\n;]+)", raw_input, re.IGNORECASE)
    if proj_match:
        fields["project_name"] = proj_match.group(1).strip('"\'  ')
        
    loc_match = re.search(r"Location[:\-]\s*([^\n;]+)", raw_input, re.IGNORECASE)
    if loc_match:
        fields["location"] = loc_match.group(1).strip('"\'  ')
        
    area_match = re.search(r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:sq\.?m|square\s*meters)", raw_input, re.IGNORECASE)
    if area_match:
        val_str = area_match.group(1).replace(",", "")
        fields["project_area_sqm"] = float(val_str)

    if re.search(r"Environmental\s*clearance\s*(?:status)?[:\-]?\s*(No|Not\s*obtained|None|False)", raw_input, re.IGNORECASE):
        fields["environmental_clearance_status"] = "No"
    elif re.search(r"Environmental\s*clearance\s*(?:status)?[:\-]?\s*(Yes|Obtained|True)", raw_input, re.IGNORECASE):
        fields["environmental_clearance_status"] = "Yes"

    if re.search(r"NOC\s*(?:status)?[:\-]?\s*(Yes|Obtained|True)", raw_input, re.IGNORECASE):
        fields["local_body_noc_status"] = "Yes"
    elif re.search(r"NOC\s*(?:status)?[:\-]?\s*(No|None|False)", raw_input, re.IGNORECASE):
        fields["local_body_noc_status"] = "No"

    go_matches = re.findall(r"GO\s*(?:\(P\))?\s*(?:No\.?\s*)?[\d\/]+(?:\/[A-Z]+)?", raw_input, re.IGNORECASE)
    if go_matches:
        fields["cited_orders"] = list(set([g.strip() for g in go_matches]))

    # Log which fields could not be extracted so caller can decide what to do
    missing_fields = [k for k, v in fields.items() if v is None]
    if missing_fields:
        logger.warning(
            f"[PDFParser] Regex fallback could not extract the following Form B-7 fields: {missing_fields}. "
            "These will be returned as None — the Planner should request clarification from the user."
        )

    return fields
