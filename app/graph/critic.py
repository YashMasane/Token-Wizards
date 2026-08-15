import re
import logging
from typing import Dict, Any, Tuple, List

logger = logging.getLogger(__name__)


def run_legal_critic_agent(
    draft_opinion: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    Audits the generated draft opinion for:
    1. Presence of the required 6 structural section headers
    2. Citation tags ([SRC-1], [SRC-2], etc.) in the draft body
    3. Actual grounding — document names from retrieved chunks must appear in the draft
       (ensures the LLM used the RAG context and did not hallucinate sources)

    Returns (is_verified: bool, feedback_message: str).
    This function does NOT silently pass everything — it reports exactly what is missing.
    """
    if not draft_opinion or not draft_opinion.strip():
        logger.error("[Critic] Draft opinion is empty — nothing to audit.")
        return False, "CRITIC FAIL: Draft opinion is empty. The synthesis agent did not produce output."

    draft_lower = draft_opinion.lower()
    issues = []

    # ── Check 1: Required section headers ────────────────────────────────────
    required_sections = [
        ("issue restatement", "## 1. Issue Restatement"),
        ("applicable provisions", "## 2. Applicable Provisions"),
        ("draft analysis", "## 3. Draft Analysis"),
        ("compliance risk", "## 4. Compliance Risk Flags"),
        ("sources", "## 5. Sources Used"),
        ("disclaimer", "## 6. Disclaimer"),
    ]
    missing_sections = [label for keyword, label in required_sections if keyword not in draft_lower]
    if missing_sections:
        issues.append(f"Missing mandatory section headers: {missing_sections}")

    # ── Check 2: Citation tags ────────────────────────────────────────────────
    citation_pattern = re.compile(r"\[SRC-\d+\]")
    found_citations = citation_pattern.findall(draft_opinion)
    if not found_citations:
        issues.append(
            "No [SRC-N] citation tags found in draft. "
            "The draft must include inline source references (e.g. [SRC-1], [SRC-2])."
        )

    # ── Check 3: RAG grounding — retrieved chunk names must appear in draft ──
    if retrieved_chunks:
        ungrounded_sources = []
        for chunk in retrieved_chunks:
            doc_name = chunk.get("document_name", "")
            doc_type = chunk.get("doc_type", "")
            # Use a short distinctive fragment of the document name for matching
            # e.g. "Kerala Building Rules" from "Kerala Building Rules, 2022"
            fragments = [w for w in doc_name.split() if len(w) > 4]
            significant_fragment = " ".join(fragments[:3]).lower() if fragments else ""
            if significant_fragment and significant_fragment not in draft_lower:
                ungrounded_sources.append(doc_name)

        # Deduplicate
        ungrounded_sources = list(dict.fromkeys(ungrounded_sources))
        if ungrounded_sources:
            issues.append(
                f"Possible hallucination risk: the following retrieved source(s) are NOT referenced "
                f"in the draft — {ungrounded_sources}. "
                "The officer must verify that cited documents match the retrieved corpus."
            )
    else:
        issues.append(
            "No retrieved chunks were passed to the Critic. "
            "RAG grounding cannot be verified — officer must manually validate all citations."
        )

    # ── Verdict ───────────────────────────────────────────────────────────────
    if issues:
        feedback = "CRITIC WARNINGS:\n" + "\n".join(f"  • {i}" for i in issues)
        logger.warning(f"[Critic] Audit completed with issues:\n{feedback}")
        # Structural section failures are hard failures; grounding warnings are soft
        structural_fail = any("Missing mandatory section" in i for i in issues)
        return not structural_fail, feedback

    feedback = (
        f"CRITIC PASS: Draft contains all 6 required sections, "
        f"{len(found_citations)} inline citation(s) [{', '.join(set(found_citations))}], "
        f"and references {len(retrieved_chunks)} retrieved source(s)."
    )
    logger.info(f"[Critic] {feedback}")
    return True, feedback
