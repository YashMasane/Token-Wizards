import re
import json
import logging
from typing import Dict, Any, Tuple, List
from app.models.llm_factory import get_llm
from app.graph.agents import AgentExecutionError

logger = logging.getLogger(__name__)


def run_legal_critic_agent(
    raw_input: str,
    draft_opinion: str,
    retrieved_chunks: List[Dict[str, Any]],
    provider: str = None,
) -> Tuple[bool, str]:
    """
    Audits the generated draft opinion using an LLM to dynamically verify:
    1. It properly answers the user's raw input query.
    2. It is logically structured using appropriate dynamic markdown headers tailored to the content.
    3. Citation tags ([SRC-1], [SRC-2], etc.) in the draft body.
    4. Actual grounding — document names from retrieved chunks must appear in the draft
       (ensures the LLM used the RAG context and did not hallucinate sources).

    Returns (is_verified: bool, feedback_message: str).
    """
    if not draft_opinion or not draft_opinion.strip():
        logger.error("[Critic] Draft opinion is empty — nothing to audit.")
        return False, "CRITIC FAIL: Draft opinion is empty. The synthesis agent did not produce output."

    logger.info("[Critic] Running LLM-based Critic Audit...")

    # Build context string for the LLM
    sources_summary = "\n".join([
        f"[{i+1}] {c.get('document_name', 'Unknown Document')}" for i, c in enumerate(retrieved_chunks)
    ]) if retrieved_chunks else "None"

    prompt = f"""You are the Chief Legal Critic for the Law Department / LSGD.
Your job is to audit a drafted legal opinion to ensure it meets strict quality standards.

USER QUERY:
{raw_input}

AVAILABLE SOURCES:
{sources_summary}

DRAFT OPINION TO AUDIT:
---
{draft_opinion}
---

You must verify the following:
1. DOES IT ANSWER THE QUERY? If the draft correctly states that it cannot answer due to missing information, this is ACCEPTABLE and should PASS. Otherwise, does the draft directly and accurately answer the user's specific query?
2. STRUCTURE: Is the response logically structured using professional Markdown headers tailored to the context (e.g. ## Summary, ## Analysis, ## Steps)? It should NOT use a rigid template if it doesn't fit the query. It should also NOT have a "Sources Used" or "References" section at the end.
3. CITATIONS: Are there inline [SRC-N] tags in the text?
4. GROUNDING: Does it rely ONLY on the Available Sources listed above? (NOTE: It is perfectly acceptable if the draft only uses a few of the sources. It does NOT need to use all of them. It just must not invent fake facts or sources).

Output your audit result as a strict JSON object with EXACTLY these two keys:
{{
  "verified": true or false,
  "feedback": "If verified is true, write a brief success message. If false, clearly and specifically explain what is missing, hallucinated, or incorrect so the drafting agent can fix it."
}}

Do NOT output any markdown blocks like ```json. Output ONLY the raw JSON object.
"""

    try:
        llm = get_llm(provider=provider, temperature=0.0)
        res = llm.invoke([{"role": "user", "content": prompt}])
        
        if not res or not res.content:
            return False, "CRITIC FAIL: Critic LLM returned an empty response."
            
        content = res.content.strip()
        # Clean up any potential markdown formatting
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        parsed = json.loads(content.strip())
        
        is_verified = bool(parsed.get("verified", False))
        feedback = parsed.get("feedback", "No feedback provided by critic.")
        
        if is_verified:
            logger.info(f"[Critic] CRITIC PASS: {feedback}")
        else:
            logger.warning(f"[Critic] CRITIC FAIL: {feedback}")
            
        return is_verified, feedback
        
    except json.JSONDecodeError as e:
        logger.error(f"[Critic] Failed to parse JSON from LLM: {res.content}")
        return False, f"CRITIC FAIL: Critic LLM returned invalid JSON. Please retry. Output was: {res.content}"
    except Exception as e:
        logger.error(f"[Critic] LLM invocation failed: {e}")
        return False, f"CRITIC FAIL: Critic LLM invocation failed: {e}"
