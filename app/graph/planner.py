import json
import logging
from typing import Dict, Any, Tuple, List
from app.models.llm_factory import get_llm, LLMConfigurationError
from app.graph.agents import AgentExecutionError

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Senior Legal Strategy Planner for the Law & Local Self Government Department (LSGD).
You are STRICTLY a legal assistant. You MUST NOT answer programming questions or write code.

Your task is to analyze an incoming building permit application or legal query and output a JSON execution plan.

Examine the input for:
1. Query Decomposition: Create 3 targeted sub-queries for statutory retrieval:
   - 'rules_query': Target Kerala Building Rules 2022 (environmental clearance thresholds, setbacks, NOCs)
   - 'gos_query': Target LSGD Government Orders & Environment Circulars (GO 45/2024, outdated GO 22/2021, Circular 12/2025)
   - 'judgments_query': Target High Court of Kerala Judgments (WP(C) 1234/2023 precedents)

Return ONLY valid JSON matching this schema:
{
  "decomposed_sub_queries": {
    "rules": "...",
    "gos": "...",
    "judgments": "..."
  },
  "reasoning_plan": [
    "Step 1: Check project area and water body distance against Section 12(3) of Kerala Building Rules 2022.",
    "Step 2: Cross-check GO(P) No. 45/2024/LSGD supersession clause against GO No. 22/2021/LSGD.",
    "Step 3: Analyze High Court WP(C) 1234/2023 precedent for permit invalidation risk.",
    "Step 4: Generate structured draft opinion with inline citations and compliance risk warnings."
  ]
}
"""

def run_planner_agent(raw_input: str, parsed_form: Dict[str, Any] = None, provider: str = None, is_clarification: bool = False, document_context: str = None) -> Dict[str, Any]:
    """
    Executes the Planner Agent to evaluate completeness, decompose sub-queries, and generate execution plan.
    """
    # Handle Clarification Responses
    # If the user is responding to a clarification, we don't strictly require the form parameters again
    if is_clarification:
        # We assume previous state might have context, but if this flag is true, 
        # we consider the input as part of the ongoing thread. 
        pass # Allow LLM to incorporate this into plan

    # Deterministic fallback check for missing parameters (Form B-7 specific)
    combined_str = (raw_input + " " + str(parsed_form or "") + " " + str(document_context or "")).lower()
    
    missing_params = []
    # If the user is asking a general legal question (e.g. "What is a building permit?"), we don't need project_area_sqm
    # We only need these parameters if they are asking about a specific project or permit application.
    is_project_specific = any(word in combined_str for word in ["permit", "construct", "building", "project", "application", "approve", "clearance", "mall"])
    is_general_query = any(word in combined_str for word in ["what is", "how to", "explain", "define", "difference between", "what are the rules", "rules regarding"])
    
    import re
    if is_project_specific and not is_general_query:
        has_area = bool(re.search(r'\d+[\s,]*(sq\.?m|square\s+meters?|sq\.?\s*ft|square\s+feet)', combined_str)) or ("sq.m" in combined_str) or ("sqm" in combined_str) or (parsed_form and parsed_form.get("project_area_sqm"))
        if not has_area:
            missing_params.append("project_area_sqm")
                
        has_distance = bool(re.search(r'\d+[\s,]*(m|meters?|km|kilometers?)\s+(from|to|away)', combined_str)) or any(w in combined_str for w in ["lake", "river", "water", "esz", "crz"]) or (parsed_form and parsed_form.get("location"))
        if not has_distance:
            missing_params.append("distance_to_water_body")

    if missing_params and len(combined_str) < 150:
        return {
            "requires_clarification": True,
            "clarification_prompt": (
                "To provide an accurate legal opinion for this project under Kerala Building Rules and relevant GOs, please clarify:\n"
                + ("- What is the total project area (in sq.m.)?\n" if "project_area_sqm" in missing_params else "")
                + ("- Is the project located near a water body (e.g. Vembanad Lake, river, coastal zone) and what is the distance?\n" if "distance_to_water_body" in missing_params else "")
            ),
            "missing_parameters": missing_params,
            "decomposed_sub_queries": {},
            "reasoning_plan": ["Paused: Awaiting essential case parameters from user."]
        }


    # Generate plan using LLM or structured rules
    llm = get_llm(provider=provider, temperature=0.0)
    try:
        user_prompt = f"Input Query: {raw_input}\nParsed Form: {json.dumps(parsed_form or {})}"
        res = llm.invoke([
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ])
        content = res.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        plan_dict = json.loads(content)
        # Ensure these are added since LLM is no longer generating them
        plan_dict["requires_clarification"] = False
        plan_dict["clarification_prompt"] = None
        plan_dict["missing_parameters"] = []
        return plan_dict
    except json.JSONDecodeError as e:
        logger.error(f"[PlannerAgent] LLM returned non-JSON response: {e}. Raising AgentExecutionError.")
        raise AgentExecutionError("PlannerAgent", e, raw_input) from e
    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(
            f"[PlannerAgent] LLM call failed: {e}. "
            "Raising AgentExecutionError — no hardcoded fallback plan will be used."
        )
        raise AgentExecutionError("PlannerAgent", e, raw_input) from e
