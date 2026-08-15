import json
import logging
from typing import Dict, Any, Tuple, List
from app.models.llm_factory import get_llm
from app.graph.agents import AgentExecutionError

logger = logging.getLogger(__name__)

SUFFICIENCY_CHECKER_PROMPT = """You are a Legal Context Sufficiency Evaluator.
Your job is to determine if the retrieved context is sufficient to answer the user's legal query.

Given the query and the retrieved context passages:
1. Is the context sufficient to answer the query accurately?
2. If NOT sufficient, provide refined search queries to retrieve better information. Focus on specific keywords, sections, or GO numbers that might have been missed.

Output MUST be valid JSON matching this schema:
{
  "is_sufficient": true | false,
  "reasoning": "Explanation of why it is or is not sufficient",
  "refined_sub_queries": {
    "rules": "Refined query for rules (only if not sufficient)",
    "gos": "Refined query for GOs (only if not sufficient)",
    "judgments": "Refined query for judgments (only if not sufficient)"
  }
}
"""

def evaluate_context_sufficiency(query: str, chunks: List[Dict[str, Any]], provider: str = None) -> Tuple[bool, Dict[str, str]]:
    """
    Evaluates if the retrieved chunks are sufficient to answer the query.
    Returns (is_sufficient, refined_sub_queries).
    """
    if not chunks:
        logger.info("[SufficiencyChecker] No chunks provided. Context is inherently insufficient.")
        return False, {
            "rules": query,
            "gos": query,
            "judgments": query
        }

    llm = get_llm(provider=provider, temperature=0.0)
    
    # Prepare context
    context_text = "\n\n".join([f"Source: {c.get('document_name', 'Unknown')}\n{c.get('content', '')}" for c in chunks[:10]])
    user_prompt = f"Query: {query}\n\nRetrieved Context:\n{context_text}"
    
    try:
        res = llm.invoke([
            {"role": "system", "content": SUFFICIENCY_CHECKER_PROMPT},
            {"role": "user", "content": user_prompt}
        ])
        content = res.content
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        parsed = json.loads(content)
        
        is_sufficient = parsed.get("is_sufficient", True)
        reasoning = parsed.get("reasoning", "No reasoning provided")
        refined_queries = parsed.get("refined_sub_queries", {})
        
        logger.info(f"[SufficiencyChecker] is_sufficient={is_sufficient}. Reasoning: {reasoning}")
        return is_sufficient, refined_queries
        
    except json.JSONDecodeError as e:
        logger.error(f"[SufficiencyChecker] LLM returned non-JSON response: {e}. Defaulting to sufficient to prevent loop.")
        return True, {}
    except Exception as e:
        logger.error(f"[SufficiencyChecker] LLM call failed: {e}. Raising AgentExecutionError.")
        raise AgentExecutionError("SufficiencyChecker", e, query) from e

