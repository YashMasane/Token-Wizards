import json
import re
import logging
from typing import Dict, Any, List, Optional

from app.models.llm_factory import get_llm, LLMConfigurationError
from app.graph.agents import AgentExecutionError
from app.graph.plan import LegalReasoningPlan, QUERY_TYPE_GENERAL

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — instructs the LLM to produce a FULLY DYNAMIC, query-specific
# JSON plan (NOT the same 4 boilerplate steps every time).
# ─────────────────────────────────────────────────────────────────────────────
PLANNER_SYSTEM_PROMPT = """You are the Senior Legal Strategy Planner for the Law & Local Self Government Department (LSGD) of Kerala.
You are STRICTLY a legal assistant. You MUST NOT answer programming questions or write code.

════════════════════════════════════════
PART A — CLARIFICATION CHECK  (HIGH BAR — default is to PROCEED)
════════════════════════════════════════
You MUST PROCEED without asking questions unless it is COMPLETELY IMPOSSIBLE to produce any useful
legal analysis with the information given.

NEVER ask for clarification on:
  ✗ General legal questions ("What is the setback rule?", "Do I need an EIA?")
  ✗ Queries that already contain enough detail to start analysis
  ✗ Optional context (water body distance, NOC status, EC status) — analyse with what you have
  ✗ Information you can assume reasonable defaults for (e.g. assume Kerala jurisdiction)

ONLY halt (requires_clarification=true) when ALL of the following are true:
  1. The query is about a SPECIFIC project or application (not a general question)
  2. AND the project area / size is completely absent (you cannot determine if EIA thresholds apply)
  3. AND the location in Kerala is completely absent (you cannot identify applicable local body rules)
  4. AND the query is so vague that even partial analysis is impossible

If the user mentions ANY of the following, that is SUFFICIENT to proceed:
  - A project type (mall, hospital, building, factory, colony, etc.)
  - A location or district in Kerala
  - A size or area estimate (even approximate)
  - A reference to a specific rule, GO, or section
  - Any specific factual detail about the project

When is_clarification=true (user is answering a previous question):
  - Extract ALL values from their answer.
  - ALWAYS set requires_clarification=false after receiving an answer — do not ask again.
  - Proceed to build the full legal plan immediately.

If you must ask, ask at most ONE focused question — the single most critical missing fact.

════════════════════════════════════════
PART B — DYNAMIC PLAN GENERATION
════════════════════════════════════════
When clarification is NOT needed, classify the query and build a precise, QUERY-SPECIFIC plan.

STEP B1 — CLASSIFY THE QUERY TYPE:
Choose the single best-fitting type from:
  • "permit_evaluation"    — A specific project seeking full compliance analysis
  • "legal_question"       — General "what does rule / section X say?" queries
  • "compliance_audit"     — Is this existing/ongoing project compliant?
  • "precedent_research"   — Search for court judgments on a specific legal issue
  • "document_review"      — Uploaded document or application needs analysis
  • "noc_clearance"        — NOC / environmental clearance specific queries
  • "setback_zone_query"   — Setback distances, CRZ, ESZ, buffer zones
  • "go_interpretation"    — Interpreting a specific Government Order
  • "appeal_or_challenge"  — Permit rejection / appeal / court challenge scenarios
  • "general"              — Fallback only when nothing else fits

STEP B2 — IDENTIFY APPLICABLE LAWS:
List the specific Kerala laws, rules, and GOs that are directly relevant. Be precise.
Examples:
  - "Kerala Building Rules 2022, Rule 12(3) — EIA threshold for commercial buildings"
  - "GO(P) No. 45/2024/LSGD — Supersession of GO No. 22/2021"
  - "Circular 12/2025/LSGD — Updated environmental NOC procedure"
  - "Kerala Conservation of Paddy Land and Wetland Act, 2008"
  - "CRZ Notification 2019, MoEFCC — Coastal zone classifications"

STEP B3 — CHOOSE RETRIEVAL STRATEGY:
  • "statutory_first"   — Prioritise Rules and Acts, then GOs, then judgments
  • "go_focused"        — Prioritise Government Orders and Circulars
  • "precedent_led"     — Start with court judgments, use statutes for context
  • "balanced"          — Distribute evenly across all source types

STEP B4 — BUILD THE STEPS:
Create 3 to 6 steps. Each step MUST be:
  ✓ Specific to THIS query (not generic boilerplate)
  ✓ Reference a concrete law, section, GO number, or judgment citation
  ✓ Have a clear, testable expected output
  ✗ NOT a copy-paste of the example steps below

Example for a mall near a river with 12,000 sq.m area:
  Step 1: Verify if 12,000 sq.m commercial area triggers mandatory EIA under Kerala Building Rules 2022, Rule 12(3) — threshold is 20,000 sq.m for commercial, but check if local body has stricter norms.
  Step 2: Determine CRZ classification for the river bank under CRZ Notification 2019 — check if project falls in CRZ-I, II, III or IV zone, each with different development restrictions.
  Step 3: Cross-verify GO(P) No. 45/2024/LSGD whether it modified setback requirements for commercial projects near classified water bodies.
  Step 4: Check if Kerala Conservation of Paddy Land and Wetland Act 2008 applies to the site — determine if wetland conversion NOC is required.
  Step 5: Search for HC precedents (WP(C) 1234/2023) on permit rejections for commercial projects near water bodies to assess litigation risk.

STEP B5 — DECOMPOSE SUB-QUERIES:
Create 3 precise retrieval sub-queries (NOT the same as the user's raw question):
  - "rules": Target Kerala Building Rules 2022 for the specific thresholds / provisions at issue
  - "gos":   Target the specific GOs / Circulars most likely to affect this query
  - "judgments": Target judgments most likely to contain a relevant precedent

════════════════════════════════════════
OUTPUT FORMAT — Return ONLY valid JSON
════════════════════════════════════════

When clarification IS needed:
{
  "requires_clarification": true,
  "clarification_prompt": "To provide an accurate legal opinion, please clarify:\\n- [specific question 1]\\n- [specific question 2]",
  "missing_parameters": ["param_name_1", "param_name_2"],
  "extracted_answers": {},
  "legal_plan": null,
  "decomposed_sub_queries": {},
  "reasoning_plan": ["Paused: Awaiting essential case parameters from user."]
}

When clarification is NOT needed:
{
  "requires_clarification": false,
  "clarification_prompt": null,
  "missing_parameters": [],
  "extracted_answers": {
    "param_name": "extracted value"
  },
  "legal_plan": {
    "query_type": "permit_evaluation",
    "applicable_laws": [
      "Kerala Building Rules 2022, Rule 12(3) — EIA thresholds",
      "GO(P) No. 45/2024/LSGD — Environmental clearance supersession"
    ],
    "retrieval_strategy": "statutory_first",
    "estimated_complexity": "high",
    "summary": "Full compliance analysis for 12,000 sq.m mall near Vembanad Lake in Alappuzha municipality",
    "steps": [
      {
        "step_id": 1,
        "action": "Check if 12,000 sq.m area triggers mandatory EIA under Kerala Building Rules 2022, Rule 12(3)",
        "target_sources": ["Rules"],
        "legal_focus": "Kerala Building Rules 2022, Rule 12(3) — area thresholds for EIA requirement",
        "expected_output": "Determination of whether EIA is mandatory with threshold comparison"
      },
      {
        "step_id": 2,
        "action": "Determine CRZ classification for the Vembanad Lake shoreline site under CRZ Notification 2019",
        "target_sources": ["Rules", "GO"],
        "legal_focus": "CRZ Notification 2019, MoEFCC — zone classification and permissible activities",
        "expected_output": "CRZ zone category and list of prohibited/restricted activities for the site"
      }
    ]
  },
  "decomposed_sub_queries": {
    "rules": "Kerala Building Rules 2022 EIA threshold commercial building area 12000 sqm environmental clearance",
    "gos": "GO(P) 45/2024 LSGD environmental clearance commercial project water body CRZ setback",
    "judgments": "High Court Kerala commercial building permit water body CRZ environmental clearance NOC refusal"
  },
  "reasoning_plan": [
    "Step 1: Check if 12,000 sq.m area triggers mandatory EIA [Kerala Building Rules 2022, Rule 12(3)]",
    "Step 2: Determine CRZ classification for the Vembanad Lake shoreline site [CRZ Notification 2019]"
  ]
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Planner Agent
# ─────────────────────────────────────────────────────────────────────────────
def run_planner_agent(
    raw_input: str,
    parsed_form: Dict[str, Any] = None,
    provider: str = None,
    is_clarification: bool = False,
    document_context: str = None,
    previous_clarification_prompt: Optional[str] = None,
    previous_missing_params: Optional[List[str]] = None,
    previous_user_answers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Executes the Planner Agent.

    Returns a dict with keys:
      requires_clarification, clarification_prompt, missing_parameters,
      extracted_answers, legal_plan (LegalReasoningPlan as dict | None),
      decomposed_sub_queries, reasoning_plan (List[str] for frontend).
    """
    previous_missing_params  = previous_missing_params  or []
    previous_user_answers    = previous_user_answers    or {}

    # ── Guard: empty input ─────────────────────────────────────────────────────
    if not raw_input or not raw_input.strip():
        return {
            "requires_clarification": True,
            "clarification_prompt": (
                "Please describe your project or legal question so I can assist you. "
                "For a building permit review, include details such as the project name, "
                "location, type of building, and approximate area."
            ),
            "missing_parameters": ["query"],
            "extracted_answers": {},
            "legal_plan": None,
            "decomposed_sub_queries": {},
            "reasoning_plan": ["Paused: Awaiting user query."],
        }

    # ── Build context prompt ───────────────────────────────────────────────────
    context_parts = [f"User Query: {raw_input}"]

    if parsed_form:
        context_parts.append(f"Structured Form Data: {json.dumps(parsed_form)}")

    if document_context:
        context_parts.append(f"Uploaded Document (excerpt): {document_context[:1000]}")

    if is_clarification and previous_clarification_prompt:
        context_parts.append(
            f"\n[CLARIFICATION CONTEXT]\n"
            f"The system previously asked:\n{previous_clarification_prompt}\n\n"
            f"Still-missing parameters: {previous_missing_params}\n"
            f"Previously collected answers: {json.dumps(previous_user_answers)}\n\n"
            f"The user's new message IS their answer. Extract values and proceed."
        )

    user_prompt = "\n\n".join(context_parts)

    # ── Invoke LLM ────────────────────────────────────────────────────────────
    llm = get_llm(provider=provider, temperature=0.1)   # slight temperature for creative plans
    res = None
    try:
        res = llm.invoke([
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ])
        raw_content = res.content or ""
        logger.debug(f"[PlannerAgent] Raw response ({len(raw_content)} chars): {raw_content[:600]}")

        content = raw_content

        # Strip markdown fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
        else:
            content = content.strip()

        # Regex fallback — grab first {...} block
        if not content or not content.startswith("{"):
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                content = match.group(0).strip()
                logger.info("[PlannerAgent] JSON extracted via regex fallback.")

        if not content:
            raise ValueError("LLM returned an empty response body.")

        plan_dict = json.loads(content)

        # ── Ensure all keys exist ──────────────────────────────────────────────
        plan_dict.setdefault("requires_clarification", False)
        plan_dict.setdefault("clarification_prompt", None)
        plan_dict.setdefault("missing_parameters", [])
        plan_dict.setdefault("extracted_answers", {})
        plan_dict.setdefault("decomposed_sub_queries", {})
        plan_dict.setdefault("legal_plan", None)
        plan_dict.setdefault("reasoning_plan", [])

        # ── Build structured LegalReasoningPlan ───────────────────────────────
        if not plan_dict["requires_clarification"]:
            raw_plan = plan_dict.get("legal_plan") or {}
            legal_plan = LegalReasoningPlan.from_llm_dict(raw_plan)
            plan_dict["legal_plan"] = legal_plan.to_dict()

            # Always regenerate reasoning_plan from structured steps for consistency
            if legal_plan.steps:
                plan_dict["reasoning_plan"] = legal_plan.to_reasoning_plan_list()

        logger.info(
            f"[PlannerAgent] requires_clarification={plan_dict['requires_clarification']}, "
            f"query_type={plan_dict.get('legal_plan', {}).get('query_type') if plan_dict.get('legal_plan') else 'N/A'}, "
            f"steps={len((plan_dict.get('legal_plan') or {}).get('steps', []))}, "
            f"extracted={list(plan_dict['extracted_answers'].keys())}"
        )
        return plan_dict

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(
            f"[PlannerAgent] JSON parse failed ({e}). "
            f"Raw response snippet: '{(res.content if res else '')[:300]}'. "
            "Falling back to minimal dynamic plan using raw query as sub-queries."
        )
        # Fallback plan — at least uses the raw query so retrieval still works
        fallback_plan = LegalReasoningPlan.from_llm_dict({
            "query_type": QUERY_TYPE_GENERAL,
            "applicable_laws": ["Kerala Building Rules 2022", "Relevant LSGD Government Orders"],
            "retrieval_strategy": "balanced",
            "estimated_complexity": "medium",
            "summary": f"Legal analysis for: {raw_input[:120]}",
            "steps": [
                {
                    "step_id": 1,
                    "action": f"Retrieve Kerala Building Rules 2022 provisions relevant to: {raw_input[:100]}",
                    "target_sources": ["Rules"],
                    "legal_focus": "Kerala Building Rules 2022 — applicable sections",
                    "expected_output": "Relevant rule provisions with section numbers",
                },
                {
                    "step_id": 2,
                    "action": "Cross-check applicable Government Orders and LSGD Circulars",
                    "target_sources": ["GO", "Circular"],
                    "legal_focus": "GO(P) No. 45/2024/LSGD and superseded orders",
                    "expected_output": "Current operative GOs with effective dates",
                },
                {
                    "step_id": 3,
                    "action": "Search High Court of Kerala judgments for directly applicable precedents",
                    "target_sources": ["Judgment"],
                    "legal_focus": "HC Kerala — relevant permit / NOC / clearance precedents",
                    "expected_output": "Key precedents with citations and ratio decidendi",
                },
                {
                    "step_id": 4,
                    "action": "Synthesise findings into a structured legal opinion with compliance risk flags",
                    "target_sources": ["Rules", "GO", "Judgment"],
                    "legal_focus": "All retrieved sources",
                    "expected_output": "Draft legal opinion with inline citations and risk ratings",
                },
            ],
        })
        return {
            "requires_clarification": False,
            "clarification_prompt": None,
            "missing_parameters": [],
            "extracted_answers": {},
            "legal_plan": fallback_plan.to_dict(),
            "decomposed_sub_queries": {
                "rules":     raw_input,
                "gos":       raw_input,
                "judgments": raw_input,
            },
            "reasoning_plan": fallback_plan.to_reasoning_plan_list(),
        }

    except AgentExecutionError:
        raise
    except Exception as e:
        logger.error(f"[PlannerAgent] LLM call failed: {e}. Raising AgentExecutionError.")
        raise AgentExecutionError("PlannerAgent", e, raw_input) from e
