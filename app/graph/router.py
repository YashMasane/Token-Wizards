import json
import logging
from typing import Dict, Any, Optional, List
from app.models.llm_factory import get_llm, LLMConfigurationError

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are the Legal Intent Routing Agent for the Law & LSGD Copilot.
Your job is to analyze the user's latest query, alongside the recent chat history, and determine the intent.

Return ONLY a valid JSON object matching this schema:
{
  "intent": "chitchat" | "form_evaluation" | "legal_query"
}

Definitions:
1. "form_evaluation": The user is explicitly asking to evaluate a specific building permit or project (e.g., they provide form details, project area, or mention evaluating a Form B-7).
2. "chitchat": The user is making conversational small talk, asking if you remember something from the history, saying hello, or asking a direct factual question that DOES NOT require searching the legal corpus (e.g., "Do you remember my name?", "Hi I am Yash", "What can you do?").
3. "legal_query": The user is asking a substantive legal question that REQUIRES searching the Kerala Building Rules or Government Orders to provide an accurate answer (e.g., "What is the setback rule?", "Do I need clearance for a 5000 sq.m building?").

Analyze the conversation carefully. If the user is just saying "Hi I am Yash", the intent is "chitchat".
"""

def run_llm_router(raw_input: str, chat_history: List[Dict[str, Any]], parsed_form: Optional[Dict[str, Any]] = None, provider: str = None) -> str:
    """
    Classifies input into one of three intents:
    - "form_b7"           → structured application evaluation (full pipeline)
    - "chitchat"          → conversational or factual query requiring no retrieval
    - "legal_query"       → substantive legal question requiring full RAG pipeline
    """
    # Deterministic check: If a structured form was explicitly passed (e.g. from UI form submission)
    if parsed_form and parsed_form.get("project_area_sqm") is not None and parsed_form.get("project_area_sqm", 0) > 0:
        logger.info("[Router] Intent=form_b7 (structured form data present)")
        return "form_b7"

    # Use a lightweight, fast model for routing if possible
    # (Fallback to default if custom logic isn't defined for the provider)
    target_model = None
    if (provider or "").lower() == "groq":
        target_model = "llama-3.1-8b-instant"
    elif (provider or "").lower() == "openai":
        target_model = "gpt-4o-mini"
        
    try:
        llm = get_llm(provider=provider, model_name=target_model, temperature=0.0)
    except Exception as e:
        logger.warning(f"[Router] Failed to init lightweight LLM: {e}. Falling back to default.")
        llm = get_llm(provider=provider, temperature=0.0)

    # Format history for context
    history_str = ""
    for msg in chat_history[-4:]:  # last 4 messages for context
        role = "User" if msg.get("role") == "user" else "Assistant"
        history_str += f"{role}: {msg.get('content')}\n"

    user_prompt = f"Chat History:\n{history_str}\n\nLatest Query:\n{raw_input}\n\nClassify the latest query."

    try:
        res = llm.invoke([
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ])
        content = res.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        result = json.loads(content)
        intent = result.get("intent", "legal_query")
        
        # Map "form_evaluation" to our internal graph logic "form_b7"
        if intent == "form_evaluation":
            intent = "form_b7"
            
        logger.info(f"[Router] LLM classified intent as '{intent}'")
        return intent
    except Exception as e:
        logger.error(f"[Router] LLM classification failed: {e}. Defaulting to 'legal_query'.")
        return "legal_query"

def classify_input_intent(raw_input: str, parsed_form: Optional[Dict[str, Any]] = None, chat_history: List[Dict[str, Any]] = None, provider: str = None) -> str:
    """
    Adapter function that maintains the original signature where possible,
    but now delegates to the LLM router.
    """
    chat_history = chat_history or []
    return run_llm_router(raw_input, chat_history, parsed_form, provider)
