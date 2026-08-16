import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.graph.state import LegalAssistantState
from app.graph.nodes import (
    security_guardrail_node,
    router_node,
    chitchat_node,
    planner_node,
    targeted_retrieval_node,
    sufficiency_check_node,
    multi_agent_evaluation_node,
    draft_synthesis_node,
    legal_critic_node
)

logger = logging.getLogger(__name__)

def route_after_guardrail_and_intent(state: LegalAssistantState) -> str:
    if not state.get("is_security_allowed", True):
        return "security_rejected"
    input_type = state.get("input_type", "legal_query")
    if input_type == "chitchat":
        return "chitchat"
    if input_type == "no_retrieval":
        # If no retrieval is needed, skip directly to synthesis
        return "synthesis"
    return "planner"

def route_after_sufficiency_check(state: LegalAssistantState) -> str:
    if state.get("requires_user_clarification"):
        return "synthesis"  # Synthesis handles sending the clarification prompt to user
    if not state.get("is_context_sufficient", True):
        return "re_retrieval"
    return "evaluation"

def route_after_critic(state: LegalAssistantState) -> str:
    """
    If the critic verifies the draft, or we've hit the loop limit, end.
    Otherwise, send it back to synthesis for revision.
    """
    if state.get("critic_verified"):
        return "end"
    if state.get("critic_iterations", 0) >= 2:
        logger.warning("[Workflow] Critic loop limit (2) reached. Outputting unverified draft.")
        return "end"
    return "synthesis"

def build_legal_assistant_graph():
    workflow = StateGraph(LegalAssistantState)
    
    # Add Nodes
    workflow.add_node("security_guardrail", security_guardrail_node)
    workflow.add_node("router", router_node)
    workflow.add_node("chitchat", chitchat_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("retrieval", targeted_retrieval_node)
    workflow.add_node("sufficiency_check", sufficiency_check_node)
    workflow.add_node("multi_agent_eval", multi_agent_evaluation_node)
    workflow.add_node("synthesis", draft_synthesis_node)
    workflow.add_node("critic", legal_critic_node)
    
    # Entry Point
    workflow.set_entry_point("security_guardrail")
    
    # Edges
    workflow.add_edge("security_guardrail", "router")
    
    workflow.add_conditional_edges(
        "router",
        route_after_guardrail_and_intent,
        {
            "security_rejected": "synthesis",
            "chitchat": "chitchat",
            "planner": "planner",
            "synthesis": "synthesis"
        }
    )
    
    workflow.add_edge("chitchat", END)
    workflow.add_edge("planner", "retrieval")
    workflow.add_edge("retrieval", "sufficiency_check")
    
    workflow.add_conditional_edges(
        "sufficiency_check",
        route_after_sufficiency_check,
        {
            "re_retrieval": "retrieval",
            "evaluation": "multi_agent_eval",
            "synthesis": "synthesis"
        }
    )
    
    workflow.add_edge("multi_agent_eval", "synthesis")
    workflow.add_edge("synthesis", "critic")
    
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "end": END,
            "synthesis": "synthesis"
        }
    )

    
    # Compile with MemorySaver Checkpointer
    checkpointer = MemorySaver()
    compiled_graph = workflow.compile(checkpointer=checkpointer)
    logger.info("Compiled Stateful Multi-Agent LangGraph with Checkpointer successfully.")
    return compiled_graph

legal_graph = build_legal_assistant_graph()
