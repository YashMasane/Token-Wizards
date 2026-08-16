"""
Legal Reasoning Plan — structured representation of the planner agent's output.

These dataclasses are used internally by the planner and stored (as plain dicts)
in the LangGraph state for downstream nodes and API streaming.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# Query type taxonomy — used to drive retrieval strategy downstream
# ─────────────────────────────────────────────────────────────────────────────
QUERY_TYPE_PERMIT_EVALUATION   = "permit_evaluation"    # Specific project needing full compliance check
QUERY_TYPE_LEGAL_QUESTION      = "legal_question"       # General "what does rule X say?" queries
QUERY_TYPE_COMPLIANCE_AUDIT    = "compliance_audit"     # Is this existing/ongoing project compliant?
QUERY_TYPE_PRECEDENT_RESEARCH  = "precedent_research"   # Searching for court judgments on an issue
QUERY_TYPE_DOCUMENT_REVIEW     = "document_review"      # Analysing an uploaded document / application
QUERY_TYPE_NOC_CLEARANCE       = "noc_clearance"        # NOC / environmental clearance specific
QUERY_TYPE_SETBACK_ZONE        = "setback_zone_query"   # Setback, CRZ, ESZ related queries
QUERY_TYPE_GO_INTERPRETATION   = "go_interpretation"   # Interpreting a specific Government Order
QUERY_TYPE_APPEAL              = "appeal_or_challenge"  # Permit rejection / appeal scenarios
QUERY_TYPE_GENERAL             = "general"              # Fallback for anything that doesn't fit above


@dataclass
class PlanStep:
    """
    A single, concrete step in the legal analysis workflow.

    Attributes
    ----------
    step_id:        Sequential number (1-based).
    action:         What must be done in plain language — query-specific, NOT generic.
    target_sources: Which document types to search (e.g. ["Rules", "GO"]).
    legal_focus:    The specific provision / section / GO being interrogated.
    expected_output: What a good result from this step looks like.
    """
    step_id: int
    action: str
    target_sources: List[str]
    legal_focus: str
    expected_output: str

    def to_display_string(self) -> str:
        """Human-readable one-liner for frontend display."""
        return f"Step {self.step_id}: {self.action} [{self.legal_focus}]"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LegalReasoningPlan:
    """
    Structured multi-step legal reasoning plan produced by the Planner Agent.

    Stored as a plain dict in LangGraph state (LangGraph requires JSON-serialisable
    state values) and reconstructed via `LegalReasoningPlan.from_dict()` when needed.

    Attributes
    ----------
    query_type:           Classification of the legal query (see QUERY_TYPE_* constants).
    applicable_laws:      Specific laws, rules, or GOs identified as relevant.
    retrieval_strategy:   How the retrieval node should prioritise sources.
    estimated_complexity: "low" | "medium" | "high" — governs how deep the analysis goes.
    steps:                Ordered list of PlanStep objects.
    summary:              One-sentence summary of what the plan will accomplish.
    """
    query_type: str
    applicable_laws: List[str]
    retrieval_strategy: str          # "statutory_first" | "go_focused" | "precedent_led" | "balanced"
    estimated_complexity: str        # "low" | "medium" | "high"
    steps: List[PlanStep]
    summary: str

    # ── Factory: build from the LLM's JSON output ─────────────────────────────
    @classmethod
    def from_llm_dict(cls, d: Dict[str, Any]) -> "LegalReasoningPlan":
        """
        Construct a LegalReasoningPlan from the raw dict returned by the planner LLM.
        Falls back to sensible defaults for any missing fields so the pipeline never
        crashes due to a partially-compliant LLM response.
        """
        raw_steps = d.get("steps", [])
        steps: List[PlanStep] = []
        for i, s in enumerate(raw_steps):
            if isinstance(s, str):
                # LLM returned plain strings — wrap them
                steps.append(PlanStep(
                    step_id=i + 1,
                    action=s,
                    target_sources=["Rules", "GO", "Judgment"],
                    legal_focus="General legal provisions",
                    expected_output="Relevant legal findings",
                ))
            elif isinstance(s, dict):
                steps.append(PlanStep(
                    step_id=s.get("step_id", i + 1),
                    action=s.get("action", f"Step {i + 1}"),
                    target_sources=s.get("target_sources", ["Rules"]),
                    legal_focus=s.get("legal_focus", ""),
                    expected_output=s.get("expected_output", ""),
                ))

        return cls(
            query_type=d.get("query_type", QUERY_TYPE_GENERAL),
            applicable_laws=d.get("applicable_laws", []),
            retrieval_strategy=d.get("retrieval_strategy", "balanced"),
            estimated_complexity=d.get("estimated_complexity", "medium"),
            steps=steps,
            summary=d.get("summary", "Legal analysis plan"),
        )

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        """Return a fully JSON-serialisable dict for LangGraph state storage."""
        return {
            "query_type": self.query_type,
            "applicable_laws": self.applicable_laws,
            "retrieval_strategy": self.retrieval_strategy,
            "estimated_complexity": self.estimated_complexity,
            "summary": self.summary,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LegalReasoningPlan":
        """Reconstruct from the dict stored in LangGraph state."""
        return cls.from_llm_dict(d)

    # ── Display helpers ───────────────────────────────────────────────────────
    def to_reasoning_plan_list(self) -> List[str]:
        """
        Convert to a simple List[str] for backward-compatible frontend display
        (the existing 'plan' SSE event expects a list of strings).
        """
        return [s.to_display_string() for s in self.steps]
