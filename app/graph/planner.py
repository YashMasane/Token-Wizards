import json
import logging
from typing import Dict, Any, Tuple, List
from app.models.llm_factory import get_llm, LLMConfigurationError
from app.graph.agents import AgentExecutionError

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Senior Legal Strategy Planner for the Law & Local Self Government Department (LSGD).
Your task is to analyze an incoming building permit application or legal query and output a JSON execution plan.

Examine the input for:
1. Missing Critical Parameters: If the user is explicitly asking you to evaluate a specific building project or permit, check if the distance to a water body or the project area is missing.
   (IMPORTANT: DO NOT ask for clarification or missing parameters if the user is just saying hello, asking a general legal question, or asking a hypothetical question. Only ask if it is a specific permit evaluation.)
2. Query Decomposition: Create 3 targeted sub-queries for statutory retrieval:
   - 'rules_query': Target Kerala Building Rules 2022 (environmental clearance thresholds, setbacks, NOCs)
   - 'gos_query': Target LSGD Government Orders & Environment Circulars (GO 45/2024, outdated GO 22/2021, Circular 12/2025)
   - 'judgments_query': Target High Court of Kerala Judgments (WP(C) 1234/2023 precedents)

Return ONLY valid JSON matching this schema:
{
  "requires_clarification": false,
  "clarification_prompt": null,
  "missing_parameters": [],
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

def run_planner_agent(raw_input: str, parsed_form: Dict[str, Any] = None, provider: str = None, is_clarification: bool = False) -> Dict[str, Any]:
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
    combined_str = (raw_input + " " + str(parsed_form or "")).lower()
    
    missing_params = []
    # If the user is asking a general legal question (e.g. "What is a building permit?"), we don't need project_area_sqm
    # We only need these parameters if they are asking about a specific project or permit application.
    is_project_specific = any(word in combined_str for word in ["permit", "construct", "building", "project", "application", "approve", "clearance"])
    is_general_query = any(word in combined_str for word in ["what is", "how to", "explain", "define", "difference between"])
    
    if is_project_specific and not is_general_query:
        if "sq.m" not in combined_str and "sqm" not in combined_str and "area" not in combined_str and not (parsed_form and parsed_form.get("project_area_sqm")):
            missing_params.append("project_area_sqm")
                
        if "lake" not in combined_str and "river" not in combined_str and "water" not in combined_str and "esz" not in combined_str and "crz" not in combined_str and not (parsed_form and parsed_form.get("location")):
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
