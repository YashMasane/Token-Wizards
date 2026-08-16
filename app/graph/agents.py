import json
import logging
from typing import List, Dict, Any, Optional
from app.models.llm_factory import get_llm, LLMConfigurationError

logger = logging.getLogger(__name__)


class AgentExecutionError(RuntimeError):
    """
    Raised when a specialised agent cannot complete its LLM call.
    Carries the agent name and original cause so callers can surface a
    meaningful error to the user instead of returning invented content.
    """
    def __init__(self, agent_name: str, cause: Exception, context: str = ""):
        self.agent_name = agent_name
        self.cause = cause
        self.context = context
        super().__init__(
            f"[{agent_name}] LLM call failed — the system cannot generate a legal opinion "
            f"at this time. Cause: {cause}. "
            f"Please check the LLM configuration (provider, API key, model name) and retry. "
            + (f"Query context: {context[:120]}..." if context else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Agent 1: Statutory & Rule Compliance Agent
# ─────────────────────────────────────────────────────────────────────────────
def run_statutory_rule_agent(
    rules_chunks: List[Dict[str, Any]],
    parsed_form: Dict[str, Any],
    query: str,
    provider: str = None,
) -> str:
    """
    Evaluates Kerala Building Rules 2022 dynamically against retrieved chunks.
    Raises AgentExecutionError if the LLM call fails — no hardcoded fallback.
    """
    logger.info(f"[StatutoryAgent] Evaluating {len(rules_chunks)} statutory rule chunks...")

    context_str = (
        "\n\n".join([
            f"[{c.get('document_name')} - {c.get('clause_or_rule')}] "
            f"(Page {c.get('page_number', 1)}):\n{c.get('content')}"
            for c in rules_chunks
        ])
        if rules_chunks
        else "No specific statutory rule chunks were retrieved for this query."
    )

    prompt = f"""You are the Statutory Rule Compliance Specialist for the Law Department & LSGD.
Analyze the following statutory building rules context against the application/query:

APPLICATION / QUERY:
{query}
Application Parameters: {json.dumps(parsed_form or {})}

RETRIEVED STATUTORY RULES CONTEXT:
{context_str}

Evaluate compliance with the applicable sections present in the retrieved context.
If no relevant chunks were retrieved, state clearly that statutory retrieval returned no results
and the officer must manually verify.

Provide a clear, formal legal analysis of statutory rule compliance based solely on the retrieved context."""

    try:
        llm = get_llm(provider=provider, temperature=0.0)
        res = llm.invoke([{"role": "user", "content": prompt}])
        if not res or not res.content:
            raise ValueError("LLM returned an empty response.")
        return res.content
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"[StatutoryAgent] LLM invocation failed: {e}. "
            "Raising AgentExecutionError — no hardcoded fallback will be used."
        )
        raise AgentExecutionError("StatutoryRuleAgent", e, query) from e


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Agent 2: GO Supersession & Timeline Tracking Agent
# ─────────────────────────────────────────────────────────────────────────────
def run_go_tracker_agent(
    go_chunks: List[Dict[str, Any]],
    parsed_form: Dict[str, Any],
    query: str,
    provider: str = None,
) -> str:
    """
    Evaluates Executive GOs & Circulars, checking supersession dynamically.
    Raises AgentExecutionError if the LLM call fails — no hardcoded fallback.
    """
    logger.info(f"[GOTrackerAgent] Evaluating {len(go_chunks)} Government Orders and Circular chunks...")

    context_str = (
        "\n\n".join([
            f"[{c.get('document_name')} - {c.get('clause_or_rule')}] "
            f"(Dated: {c.get('doc_date', 'N/A')}):\n{c.get('content')}"
            for c in go_chunks
        ])
        if go_chunks
        else "No Government Order or Circular chunks were retrieved for this query."
    )

    prompt = f"""You are the Executive Order & Supersession Tracking Specialist for LSGD.
Analyze the following Executive Government Orders & Circulars context:

APPLICATION / QUERY:
{query}
Application Parameters: {json.dumps(parsed_form or {})}

RETRIEVED GOs & CIRCULARS CONTEXT:
{context_str}

Evaluate the applicable Government Orders present in the retrieved context, including any supersession
relationships between orders. If no relevant chunks were retrieved, state clearly that GO retrieval
returned no results and the officer must manually verify.

Provide a formal executive timeline and supersession tracking analysis based solely on the retrieved context."""

    try:
        llm = get_llm(provider=provider, temperature=0.0)
        res = llm.invoke([{"role": "user", "content": prompt}])
        if not res or not res.content:
            raise ValueError("LLM returned an empty response.")
        return res.content
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"[GOTrackerAgent] LLM invocation failed: {e}. "
            "Raising AgentExecutionError — no hardcoded fallback will be used."
        )
        raise AgentExecutionError("GOTrackerAgent", e, query) from e


# ─────────────────────────────────────────────────────────────────────────────
# Specialized Agent 3: Judicial Precedent & Legal Risk Agent
# ─────────────────────────────────────────────────────────────────────────────
def run_judicial_precedent_agent(
    judgment_chunks: List[Dict[str, Any]],
    parsed_form: Dict[str, Any],
    query: str,
    provider: str = None,
) -> str:
    """
    Evaluates High Court judgments for legal liability & quashing risks.
    Raises AgentExecutionError if the LLM call fails — no hardcoded fallback.
    """
    logger.info(f"[PrecedentAgent] Evaluating {len(judgment_chunks)} court judgment chunks...")

    context_str = (
        "\n\n".join([
            f"[{c.get('document_name')} - {c.get('clause_or_rule')}] "
            f"(Page {c.get('page_number', 1)}):\n{c.get('content')}"
            for c in judgment_chunks
        ])
        if judgment_chunks
        else "No court judgment chunks were retrieved for this query."
    )

    prompt = f"""You are the Judicial Precedent & Legal Liability Specialist for the Law Department.
Analyze the following court judgment context:

APPLICATION / QUERY:
{query}
Application Parameters: {json.dumps(parsed_form or {})}

RETRIEVED CASE LAW CONTEXT:
{context_str}

Evaluate the judicial precedents present in the retrieved context, including holdings on permit validity,
officer liability, and demolition orders. If no relevant judgment chunks were retrieved, state clearly
that judgment retrieval returned no results and the officer must manually verify.

Provide a formal legal precedent risk analysis based solely on the retrieved context."""

    try:
        llm = get_llm(provider=provider, temperature=0.0)
        res = llm.invoke([{"role": "user", "content": prompt}])
        if not res or not res.content:
            raise ValueError("LLM returned an empty response.")
        return res.content
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"[PrecedentAgent] LLM invocation failed: {e}. "
            "Raising AgentExecutionError — no hardcoded fallback will be used."
        )
        raise AgentExecutionError("JudicialPrecedentAgent", e, query) from e


# ─────────────────────────────────────────────────────────────────────────────
# Synthesis & Draft Generator Agent
# ─────────────────────────────────────────────────────────────────────────────
def run_draft_synthesis_agent(
    raw_input: str,
    parsed_form: Dict[str, Any],
    statutory_findings: str,
    go_findings: str,
    precedent_findings: str,
    risk_flags: List[Dict[str, Any]],
    sources_used: List[Dict[str, Any]],
    provider: str = None,
    document_context: str = None,
    document_filename: str = None,
    previous_draft: str = None,
    critic_feedback: str = None,
) -> str:
    """
    Synthesizes agent findings into the mandatory 6-part standardized legal draft opinion.
    If previous_draft and critic_feedback are provided, acts as a revision step.
    Raises AgentExecutionError if the LLM call fails — no hardcoded fallback.
    """
    logger.info("[DraftSynthesis] Compiling multi-agent findings into standardized 6-part legal opinion...")

    sources_summary = json.dumps(
        [
            {
                "doc_id": s.get("doc_id"),
                "name": s.get("document_name"),
                "type": s.get("doc_type"),
                "clause": s.get("clause_or_rule"),
                "page": s.get("page_number", 1),
                "url": s.get("download_url"),
            }
            for s in sources_used
        ],
        indent=2,
    )

    # Build optional user-document section
    doc_section = ""
    if document_context:
        fname = document_filename or "Uploaded Document"
        # Truncate to avoid blowing context window (approx 6000 words ~ 8000 tokens)
        truncated = document_context[:24000]
        doc_section = f"""

USER-UPLOADED DOCUMENT — "{fname}" (Analyse this document and answer the user's query in relation to it):
---
{truncated}
---
"""

    critic_section = ""
    if critic_feedback and previous_draft:
        critic_section = f"""
CRITICAL REVISION REQUIRED:
The previous draft you generated failed the legal critic audit.
Critic Feedback: {critic_feedback}

Your task is to REWRITE the draft to explicitly address this feedback. Do not repeat the same mistakes.
"""

    prompt = f"""You are the Lead Legal Draft Officer for the Law Department / LSGD.
Synthesize the following evaluation into a professional, logically structured markdown response.
{critic_section}
INPUT QUERY / APPLICATION:
{raw_input}
Parsed Application Details: {json.dumps(parsed_form or {})}{doc_section}

AGENT FINDINGS:
1. Statutory Agent Findings: {statutory_findings}
2. GO Tracker Agent Findings: {go_findings}
3. Precedent Agent Findings: {precedent_findings}

COMPLIANCE RISK FLAGS:
{json.dumps(risk_flags, indent=2)}

RETRIEVED SOURCES:
{sources_summary}

INSTRUCTIONS:
1. Dynamic Structure: Analyze the user's intent. Instead of a fixed format, create a logical and professional markdown structure that directly answers the user's query. Use clear markdown headers (e.g., `## Summary`, `## Analysis`, `## Step-by-Step Guide`) that fit the context.
2. Grounding & Citations: Base your response ONLY on the Agent Findings and Retrieved Sources above. Do not hallucinate facts.
3. Inline Citations: You MUST use inline citations in the format [SRC-N] for every factual claim.
4. No Sources Section: Do NOT include a "Sources Used" or "References" section at the end of your response. The system UI will append the bibliography automatically.
5. Strict Anti-Hallucination: If the Agent Findings indicate that no relevant rules, GOs, or precedents were found, you MUST explicitly refuse to answer the core legal question and state that the system lacks the specific statutory context. Do NOT invent a general checklist, process, or steps out of thin air.
"""

    # Return both the LLM text AND the structured sources list
    # The sources are returned separately so the frontend can render them as proper HTML links
    def _build_structured_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for s in sources:
            doc_id = s.get("doc_id", "")
            if doc_id in seen:
                continue
            seen.add(doc_id)
            result.append({
                "name": s.get("document_name", "Unknown"),
                "type": s.get("doc_type", "-"),
                "clause": s.get("clause_or_rule", "-"),
                "page": s.get("page_number", 1),
                "url": s.get("download_url") or "",
            })
        return result

    try:
        llm = get_llm(provider=provider, temperature=0.0)
        res = llm.invoke([{"role": "user", "content": prompt}])
        if not res or not res.content:
            raise ValueError("LLM returned an empty response.")
        
        output = res.content.strip()
        # Return a tuple: (text_output, structured_sources)
        return output, _build_structured_sources(sources_used)
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"[DraftSynthesis] LLM invocation failed: {e}. "
            "Raising AgentExecutionError — no hardcoded fallback will be used."
        )
        raise AgentExecutionError("DraftSynthesisAgent", e, raw_input) from e


# ─────────────────────────────────────────────────────────────────────────────
# Conversational / Chitchat Agent (No Retrieval)
# ─────────────────────────────────────────────────────────────────────────────
def run_chitchat_agent(
    raw_input: str,
    chat_history: List[Dict[str, Any]],
    provider: str = None,
) -> str:
    """
    Handles conversational interactions and factual queries that do not require
    searching the legal corpus. Maintains conversational memory.
    """
    logger.info("[ChitchatAgent] Generating conversational response...")

    # Format history
    history_str = ""
    for msg in chat_history[-6:]:  # last 6 messages for context
        role = "User" if msg.get("role") == "user" else "Assistant"
        history_str += f"{role}: {msg.get('content')}\n"

    prompt = f"""You are a helpful, friendly AI Copilot for the Law Department and Local Self Government Department (LSGD) in Kerala.
You are STRICTLY a legal assistant. You MUST NOT answer general programming questions, write code (e.g., Python, JavaScript), or respond to non-legal technical queries. If the user asks for code or non-legal help, politely decline and remind them that you are a legal assistant exclusively for LSGD and Law Department matters.

You are currently engaged in a conversation with a user (likely a legal officer). 

Chat History:
{history_str}

User's Latest Message:
{raw_input}

Respond directly to the user's latest message in a helpful and conversational tone. 
If they ask for your capabilities, explain that you can evaluate Form B-7 applications against Kerala Building Rules 2022, check Government Orders, and search High Court precedents.
Do not invent any legal advice. If they ask a complex legal question here, politely inform them to ask it clearly so the system can run a full retrieval analysis."""

    try:
        # We can use the lightweight model for chitchat too for speed
        target_model = None
        if (provider or "").lower() == "groq":
            target_model = "llama-3.1-8b-instant"
        elif (provider or "").lower() == "openai":
            target_model = "gpt-4o-mini"
            
        try:
            llm = get_llm(provider=provider, model_name=target_model, temperature=0.3)
        except Exception:
            llm = get_llm(provider=provider, temperature=0.3)
            
        res = llm.invoke([{"role": "user", "content": prompt}])
        if not res or not res.content:
            raise ValueError("LLM returned an empty response.")
        return res.content
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(f"[ChitchatAgent] LLM invocation failed: {e}")
        raise AgentExecutionError("ChitchatAgent", e, raw_input) from e
