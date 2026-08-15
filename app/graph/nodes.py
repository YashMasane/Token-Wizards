import logging
from typing import Dict, Any
from app.graph.state import LegalAssistantState
from app.guardrail import evaluate_security_and_scope
from app.graph.router import classify_input_intent
from app.graph.planner import run_planner_agent
from app.services.hybrid_retriever import hybrid_retriever
from app.services.context_compressor import deduplicate_and_partition_chunks
from app.services.compliance_engine import run_deterministic_compliance_checks
from app.services.web_search import perform_fallback_web_search
from app.graph.agents import (
    run_statutory_rule_agent,
    run_go_tracker_agent,
    run_judicial_precedent_agent,
    run_draft_synthesis_agent,
    run_chitchat_agent,
    AgentExecutionError,
)
from app.graph.critic import run_legal_critic_agent
from app.models.llm_factory import LLMConfigurationError
from app.services.reranker import reranker_service
from app.services.sufficiency_checker import evaluate_context_sufficiency

logger = logging.getLogger(__name__)


def _format_system_error(error: Exception) -> str:
    """Formats a system-level error into a user-facing Markdown message."""
    return (
        "# ⚠️ System Error — Legal Analysis Could Not Be Completed\n\n"
        "The multi-agent legal analysis system encountered an error and **cannot generate a response** "
        "using invented or hardcoded content.\n\n"
        f"**Error Details:**\n```\n{error}\n```\n\n"
        "**Recommended Actions:**\n"
        "1. Check that your LLM API key is valid and not expired (see `.env` → `GROQ_API_KEY` / `OPENAI_API_KEY`).\n"
        "2. Verify your internet connection and LLM provider status.\n"
        "3. Call `GET /api/health` to check the LLM connectivity status.\n"
        "4. Review server logs for the full error traceback.\n\n"
        "_This message is shown because the system is configured to surface failures rather than "
        "return potentially incorrect hardcoded responses._"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Security Guardrail Node
# ─────────────────────────────────────────────────────────────────────────────
def security_guardrail_node(state: LegalAssistantState) -> Dict[str, Any]:
    raw_input = state["raw_input"]
    model_provider = state.get("model_provider")
    logger.info(f"[Node: SecurityGuardrail] Evaluating security and scope for input length: {len(raw_input)}")
    is_allowed, msg = evaluate_security_and_scope(raw_input, provider=model_provider)
    return {
        "is_security_allowed": is_allowed,
        "security_warning": msg if not is_allowed else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Intelligent Router Node
# ─────────────────────────────────────────────────────────────────────────────
def router_node(state: LegalAssistantState) -> Dict[str, Any]:
    if not state.get("is_security_allowed", True):
        logger.warning("[Node: Router] Security rejected input. Routing to security_violation.")
        return {"input_type": "security_violation"}

    raw_input = state["raw_input"]
    parsed_form = state.get("parsed_form")
    chat_history = state.get("chat_history", [])
    model_provider = state.get("model_provider")
    
    input_type = classify_input_intent(raw_input, parsed_form, chat_history, model_provider)
    logger.info(f"[Node: Router] Classified input intent as '{input_type}'")
    return {"input_type": input_type}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: Chitchat Direct Response Node
# ─────────────────────────────────────────────────────────────────────────────
def chitchat_node(state: LegalAssistantState) -> Dict[str, Any]:
    logger.info("[Node: Chitchat] Generating conversational response...")
    raw_input = state["raw_input"]
    chat_history = state.get("chat_history", [])
    model_provider = state.get("model_provider")
    
    try:
        chitchat_response = run_chitchat_agent(raw_input, chat_history, model_provider)
    except (AgentExecutionError, LLMConfigurationError) as e:
        logger.error(f"[Node: Chitchat] Agent failed: {e}")
        chitchat_response = _format_system_error(e)
        
    return {
        "final_markdown_output": chitchat_response,
        "requires_user_clarification": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Planner Agent Node
# ─────────────────────────────────────────────────────────────────────────────
def planner_node(state: LegalAssistantState) -> Dict[str, Any]:
    logger.info("[Node: Planner] Running Planner Agent for query decomposition & strategy planning...")
    raw_input = state["raw_input"]
    parsed_form = state.get("parsed_form") or {}
    is_clarification = state.get("input_type") == "clarification_answer"

    document_context = state.get("document_context")

    try:
        plan_data = run_planner_agent(
            raw_input, 
            parsed_form, 
            provider=state.get("model_provider"), 
            is_clarification=is_clarification,
            document_context=document_context
        )
    except (AgentExecutionError, LLMConfigurationError) as e:
        logger.error(f"[Node: Planner] Planning failed: {e}")
        error_msg = _format_system_error(e)
        return {
            "system_error": str(e),
            "final_markdown_output": error_msg,
            "requires_user_clarification": False,
        }

    logger.info(
        f"[Node: Planner] Requires clarification: {plan_data.get('requires_clarification', False)}. "
        f"Decomposed sub-queries count: {len(plan_data.get('decomposed_sub_queries', {}))}"
    )
    return {
        "requires_user_clarification": plan_data.get("requires_clarification", False),
        "clarification_prompt": plan_data.get("clarification_prompt"),
        "missing_parameters": plan_data.get("missing_parameters", []),
        "decomposed_sub_queries": plan_data.get("decomposed_sub_queries", {}),
        "reasoning_plan": plan_data.get("reasoning_plan", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: Sub-Query Targeted Retrieval Node
# ─────────────────────────────────────────────────────────────────────────────
def targeted_retrieval_node(state: LegalAssistantState) -> Dict[str, Any]:
    # Short-circuit if a system error was already recorded upstream
    if state.get("system_error"):
        logger.info("[Node: Retrieval] Skipped — system error already recorded.")
        return {}

    if state.get("requires_user_clarification"):
        logger.info("[Node: Retrieval] Skipped due to pending user clarification.")
        return {}

    sub_queries = state.get("refined_sub_queries") or state.get("decomposed_sub_queries", {})
    raw_input = state["raw_input"]

    rules_q = sub_queries.get("rules") or raw_input
    gos_q = sub_queries.get("gos") or raw_input
    judgments_q = sub_queries.get("judgments") or raw_input

    # Ensure they are strings (LLM might sometimes generate dicts/lists for these keys)
    rules_q = str(rules_q) if not isinstance(rules_q, str) else rules_q
    gos_q = str(gos_q) if not isinstance(gos_q, str) else gos_q
    judgments_q = str(judgments_q) if not isinstance(judgments_q, str) else judgments_q

    iteration = state.get("retrieval_iteration", 0) + 1

    logger.info(f"[Node: Retrieval] Running sub-query retrieval (Iteration {iteration}). Rules sub-query: '{rules_q[:60]}...'")

    # Run sub-query targeted searches
    rules_chunks = hybrid_retriever.hybrid_search(rules_q, top_k=7, doc_type_filter="Rules")
    go_chunks = hybrid_retriever.hybrid_search(gos_q, top_k=5, doc_type_filter="Government Order")
    circ_chunks = hybrid_retriever.hybrid_search(gos_q, top_k=2, doc_type_filter="Circular")
    judgment_chunks = hybrid_retriever.hybrid_search(judgments_q, top_k=4, doc_type_filter="Judgment")

    all_chunks = rules_chunks + go_chunks + circ_chunks + judgment_chunks
    logger.info(
        f"[Node: Retrieval] Retrieved {len(rules_chunks)} Rules, {len(go_chunks)+len(circ_chunks)} GOs/Circulars, "
        f"{len(judgment_chunks)} Judgments (Total: {len(all_chunks)} chunks)."
    )

    # Fallback Web Search if local context is completely sparse
    web_fallback_used = False
    if len(all_chunks) < 3:
        logger.info("[Node: Retrieval] Local corpus returned insufficient chunks. Executing fallback web search.")
        web_results = perform_fallback_web_search(raw_input)
        web_fallback_used = True

        if web_results:
            logger.info(f"[Node: Retrieval] Web search returned {len(web_results)} results. Formatting as pseudo-chunks.")
            for i, r in enumerate(web_results):
                all_chunks.append({
                    "chunk_id": f"web_{i}",
                    "doc_id": f"web_{i}",
                    "document_name": r.get("title", f"Web Result {i}"),
                    "doc_type": "WebSearch",
                    "issuing_authority": r.get("source", "Web"),
                    "doc_date": "N/A",
                    "is_outdated": False,
                    "superseded_by": None,
                    "page_number": 1,
                    "heading": r.get("title", ""),
                    "clause_or_rule": "Web Search Result",
                    "content": r.get("snippet", ""),
                    "download_url": r.get("url", ""),
                    "rrf_score": 1.0  # Base score for web results
                })
        else:
            logger.warning("[Node: Retrieval] Web search also returned 0 results. Proceeding with sparse context.")

    # 3. Reranking Phase (Cross-Encoder)
    reranked = reranker_service.rerank(raw_input, all_chunks, top_n=15)

    # 4. Compression & Filtering Phase (Filter out chunks with score < 2.0)
    partitioned = deduplicate_and_partition_chunks(reranked, min_score_threshold=2.0)
    filtered_count = partitioned.pop("filtered_out_count", 0)
    
    final_chunks = partitioned.get("all_chunks", [])
    
    # Calculate a proxy for confidence (avg of top 3 scores)
    avg_score = 0.0
    if final_chunks:
        top_scores = [c.get("rerank_score", c.get("rrf_score", 0)) for c in final_chunks[:3]]
        avg_score = sum(top_scores) / len(top_scores)

    return {
        "retrieved_chunks": all_chunks,
        "reranked_chunks": reranked,
        "partitioned_context": partitioned,
        "retrieval_confidence": round(avg_score, 2) if avg_score > 0 else (0.40 if web_fallback_used else 0.10),
        "web_fallback_used": web_fallback_used,
        "retrieval_iteration": iteration,
        "chunks_filtered_count": filtered_count
    }


def sufficiency_check_node(state: LegalAssistantState) -> Dict[str, Any]:
    logger.info("Executing Node: sufficiency_check_node")
    if state.get("system_error"):
        return {}
        
    if state.get("requires_user_clarification"):
        return {}

    chunks = state.get("partitioned_context", {}).get("all_chunks", [])
    iteration = state.get("retrieval_iteration", 1)
    
    # Max 2 retrieval iterations to prevent loops
    if iteration >= 2:
        logger.info("[Node: SufficiencyCheck] Max retrieval iterations reached. Proceeding with current context.")
        return {"is_context_sufficient": True, "refined_sub_queries": {}}
        
    try:
        is_sufficient, refined_queries = evaluate_context_sufficiency(
            state["raw_input"], 
            chunks, 
            provider=state.get("model_provider")
        )
        return {
            "is_context_sufficient": is_sufficient,
            "refined_sub_queries": refined_queries
        }
    except AgentExecutionError as e:
        logger.error(f"[Node: SufficiencyCheck] Failed: {e}. Defaulting to sufficient.")
        return {"is_context_sufficient": True, "refined_sub_queries": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Node 6: Multi-Agent Evaluation & Compliance Check Node
# ─────────────────────────────────────────────────────────────────────────────
def multi_agent_evaluation_node(state: LegalAssistantState) -> Dict[str, Any]:
    # Short-circuit if a system error was already recorded upstream
    if state.get("system_error"):
        logger.info("[Node: MultiAgentEval] Skipped — system error already recorded.")
        return {}

    if state.get("requires_user_clarification"):
        logger.info("[Node: MultiAgentEval] Skipped due to pending user clarification.")
        return {}

    logger.info("[Node: MultiAgentEval] Running domain-targeted evaluation sub-agents and deterministic compliance engine...")
    partitioned = state.get("partitioned_context", {})
    parsed_form = state.get("parsed_form") or {}
    raw_input = state["raw_input"]
    model_provider = state.get("model_provider")

    statutory_rules = partitioned.get("statutory_rules", [])
    go_orders = partitioned.get("go_orders", [])
    judgments = partitioned.get("judgments", [])

    try:
        stat_findings = run_statutory_rule_agent(statutory_rules, parsed_form, raw_input, provider=model_provider)
        go_findings = run_go_tracker_agent(go_orders, parsed_form, raw_input, provider=model_provider)
        prec_findings = run_judicial_precedent_agent(judgments, parsed_form, raw_input, provider=model_provider)
    except (AgentExecutionError, LLMConfigurationError) as e:
        logger.error(f"[Node: MultiAgentEval] Agent execution failed: {e}")
        error_msg = _format_system_error(e)
        return {
            "system_error": str(e),
            "final_markdown_output": error_msg,
        }

    # Run deterministic compliance risk engine (pure logic — never fails)
    risk_flags = run_deterministic_compliance_checks(parsed_form, raw_input)
    logger.info(f"[Node: MultiAgentEval] Compliance Engine detected {len(risk_flags)} compliance risk warnings.")

    return {
        "statutory_findings": stat_findings,
        "go_findings": go_findings,
        "precedent_findings": prec_findings,
        "compliance_risk_flags": risk_flags,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 7: Draft Synthesis & Critic Node
# ─────────────────────────────────────────────────────────────────────────────
def draft_synthesis_node(state: LegalAssistantState) -> Dict[str, Any]:
    # If a system error was recorded earlier, surface it — don't try to synthesize
    if state.get("system_error"):
        error_output = state.get("final_markdown_output") or _format_system_error(
            RuntimeError(state["system_error"])
        )
        logger.error("[Node: DraftSynthesis] System error detected in upstream state. Surfacing error to user.")
        return {
            "draft_opinion": error_output,
            "final_markdown_output": error_output,
            "critic_verified": False,
            "critic_feedback": "Critic skipped — system error occurred upstream.",
        }

    if not state.get("is_security_allowed", True):
        warning_msg = state.get("security_warning") or "Security violation: Access Denied."
        logger.warning("[Node: DraftSynthesis] Returning security boundary rejection output.")
        return {
            "draft_opinion": warning_msg,
            "final_markdown_output": warning_msg,
            "critic_verified": True,
        }

    if state.get("requires_user_clarification"):
        logger.info("[Node: DraftSynthesis] Emitting user clarification prompt.")
        return {
            "final_markdown_output": f"### Information Required\n\n{state.get('clarification_prompt')}"
        }

    logger.info("[Node: DraftSynthesis] Synthesizing 6-part standardized draft opinion and running Legal Critic audit...")
    raw_input = state["raw_input"]
    parsed_form = state.get("parsed_form") or {}
    stat_findings = state.get("statutory_findings", "")
    go_findings = state.get("go_findings", "")
    prec_findings = state.get("precedent_findings", "")
    risk_flags = state.get("compliance_risk_flags", [])
    chunks = state.get("retrieved_chunks", [])
    model_provider = state.get("model_provider")

    try:
        result = run_draft_synthesis_agent(
            raw_input, parsed_form, stat_findings, go_findings, prec_findings,
            risk_flags, chunks, provider=model_provider,
            document_context=state.get("document_context"),
            document_filename=state.get("document_filename"),
        )
        # agent now returns a (text, sources_list) tuple
        if isinstance(result, tuple):
            draft, structured_sources = result
        else:
            draft, structured_sources = result, []
    except (AgentExecutionError, LLMConfigurationError) as e:
        logger.error(f"[Node: DraftSynthesis] Synthesis agent failed: {e}")
        error_msg = _format_system_error(e)
        return {
            "draft_opinion": error_msg,
            "final_markdown_output": error_msg,
            "critic_verified": False,
            "critic_feedback": f"Critic skipped — synthesis failed: {e}",
        }

    # Run Self-Reflective Critic Audit
    verified, critic_feedback = run_legal_critic_agent(draft, chunks)
    logger.info(f"[Node: DraftSynthesis] Legal Critic audit result: Verified={verified}, Feedback: '{critic_feedback[:100]}'")

    return {
        "draft_opinion": draft,
        "critic_verified": verified,
        "critic_feedback": critic_feedback,
        "final_markdown_output": draft,
        "sources_used": structured_sources,
    }
