from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class LegalQueryRequest(BaseModel):
    query: str = Field(..., description="Legal question or prompt from officer")
    thread_id: Optional[str] = Field(default="default_session", description="Unique session thread ID")
    model_provider: Optional[str] = Field(default=None, description="Optional provider override (groq/openai/ollama)")
    model_name: Optional[str] = Field(default=None, description="Optional specific model override")
    is_clarification_response: Optional[bool] = Field(default=False, description="Flag indicating if this is an answer to a clarification request")

class FormB7Application(BaseModel):
    project_name: str = Field(..., description="Name of the commercial project")
    location: str = Field(..., description="Project location and water body proximity")
    project_area_sqm: float = Field(..., description="Total project area in square meters")
    environmental_clearance_status: str = Field(..., description="Yes/No or status details")
    local_body_noc_status: str = Field(..., description="Yes/No status")
    applicant_declaration: Optional[str] = Field(default="All mandatory approvals are in place")
    cited_orders: Optional[List[str]] = Field(default_factory=list)

class ApplicationAnalysisRequest(BaseModel):
    form_data: FormB7Application
    thread_id: Optional[str] = Field(default="default_session")
    model_provider: Optional[str] = Field(default=None)
    model_name: Optional[str] = Field(default=None)


class ComplianceCheckResult(BaseModel):
    check_type: str # "missing_approval" | "outdated_reference" | "precedent_risk"
    severity: str # "high" | "medium" | "low"
    message: str
    triggered_by: Dict[str, Any]
    relevant_sources: List[str]

class SourceCitation(BaseModel):
    ref_tag: str # e.g. "[SRC-1]"
    document_name: str
    doc_type: str
    clause_or_rule: str
    page_number: Optional[int] = 1
    quoted_snippet: str
    download_url: str

class LegalOpinionOutput(BaseModel):
    thread_id: str
    issue_restatement: str
    applicable_provisions: List[str]
    draft_analysis: str
    compliance_risk_flags: List[ComplianceCheckResult]
    sources_used: List[SourceCitation]
    disclaimer: str
    agent_reasoning_plan: List[str]
    requires_user_clarification: bool = False
    clarification_prompt: Optional[str] = None
    full_formatted_markdown: str

class SecurityCheckResponse(BaseModel):
    is_allowed: bool
    reason: Optional[str] = None
