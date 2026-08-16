from typing import List, Dict, Any, Optional, TypedDict

class LegalAssistantState(TypedDict):
    thread_id: str
    raw_input: str
    input_type: str # "form_b7" | "legal_query" | "chitchat" | "clarification_answer"
    parsed_form: Optional[Dict[str, Any]]
    chat_history: List[Dict[str, str]]
    model_provider: Optional[str]  # provider override from API request (groq/openai/ollama)
    model_name: Optional[str]      # model name override from API request
    document_context: Optional[str]   # Full text of user-uploaded document (Approach B)
    document_filename: Optional[str]  # Original filename for display
    is_clarification_response: bool   # True when the user is answering a clarification question
    user_answers: Dict[str, str]      # Accumulated clarification answers keyed by parameter name
    
    # Planner Agent Artifacts
    system_error: Optional[str]  # Set when an unrecoverable system error occurs; propagates through graph
    is_security_allowed: bool
    security_warning: Optional[str]
    missing_parameters: List[str]
    requires_user_clarification: bool
    clarification_prompt: Optional[str]
    legal_plan: Optional[Dict[str, Any]]  # Structured LegalReasoningPlan dict from planner agent
    reasoning_plan: List[str]             # Flat display strings derived from legal_plan.steps
    decomposed_sub_queries: Dict[str, str] # e.g. {"rules": "...", "gos": "...", "judgments": "..."}

    
    # Retrieval Artifacts
    retrieved_chunks: List[Dict[str, Any]]
    reranked_chunks: List[Dict[str, Any]]
    partitioned_context: Dict[str, Any]
    retrieval_confidence: float
    web_fallback_used: bool
    retrieval_iteration: int
    chunks_filtered_count: int
    
    # Sufficiency Artifacts
    is_context_sufficient: bool
    refined_sub_queries: Dict[str, str]
    
    # Domain Agent Findings
    statutory_findings: Optional[str]
    go_findings: Optional[str]
    precedent_findings: Optional[str]
    compliance_risk_flags: List[Dict[str, Any]]
    
    # Synthesis & Critique Loop
    draft_opinion: Optional[str]
    sources_used: List[Dict[str, Any]]
    critic_verified: bool
    critic_feedback: Optional[str]
    critic_iterations: int
    final_markdown_output: Optional[str]
