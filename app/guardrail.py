import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt Injection Patterns — each entry is (pattern_regex, attack_category)
# ─────────────────────────────────────────────────────────────────────────────
INJECTION_PATTERNS = [
    # Classic instruction-override attacks
    (r"ignore\s+(?:all\s+)?(?:previous|system)\s+(?:instructions|prompts)", "instruction_override"),
    (r"forget\s+(?:about\s+)?(?:the\s+)?system\s+prompt", "instruction_override"),
    (r"disregard\s+(?:previous|above|all)\s+instructions", "instruction_override"),
    (r"override\s+(?:your\s+)?(?:previous\s+)?instructions", "instruction_override"),

    # Role-reassignment attacks
    (r"(?:you\s+are\s+now|act\s+as|behave\s+as|pretend\s+(?:you\s+are|to\s+be))\s+(?:a\s+|an\s+)?(?:different|new|unrestricted|evil|free)", "role_reassignment"),
    (r"act\s+as\s+a\s+DAN", "role_reassignment"),
    (r"you\s+are\s+no\s+longer\s+(?:an?\s+)?(?:AI|assistant|bot|model)", "role_reassignment"),
    (r"switch\s+(?:to\s+)?(?:developer|admin|root|god)\s+mode", "role_reassignment"),
    (r"enable\s+(?:developer|jailbreak|unrestricted)\s+mode", "role_reassignment"),

    # System prompt extraction / data exfiltration
    (r"(?:give|show|print|tell|reveal|repeat|output|display)\s+(?:me\s+)?(?:your\s+)?system\s+prompt", "exfiltration"),
    (r"(?:what\s+(?:are|were)\s+your|print\s+(?:the\s+)?)\s*(?:initial\s+)?instructions", "exfiltration"),
    (r"(?:repeat|echo)\s+everything\s+(?:above|before)", "exfiltration"),
    (r"tell\s+me\s+(?:your\s+)?(?:confidential|hidden|secret)\s+(?:instructions|prompt|rules)", "exfiltration"),

    # Jailbreak keywords
    (r"\bjailbreak\b", "jailbreak"),
    (r"\bDAN\b", "jailbreak"),  # "Do Anything Now"

    # Code execution / lateral functionality
    (r"write\s+(?:python|javascript|sql|bash|shell|code)\s+(?:script|code|program|function)\s+(?:to|for|that)", "code_execution"),
    (r"execute\s+(?:this\s+)?(?:code|script|command)", "code_execution"),
    (r"run\s+(?:this\s+)?(?:code|shell|command)", "code_execution"),

    # Indirect / document-embedded injection markers
    (r"---\s*(?:new\s+)?system\s+prompt\s*---", "indirect_injection"),
    (r"\[INST\].*?\[/INST\]", "indirect_injection"),           # LLM instruction tags
    (r"<\|system\|>|<\|user\|>|<\|assistant\|>", "indirect_injection"),  # special tokens

    # Token manipulation
    (r"(?:base64|hex|rot13|encoded)\s+(?:instruction|command|prompt)", "encoding_attack"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Out-of-Domain patterns — blatant off-topic, not injection but clearly OOD
# ─────────────────────────────────────────────────────────────────────────────
OUT_OF_DOMAIN_PATTERNS = [
    (r"tell\s+me\s+a\s+(?:joke|story|riddle)", "off_topic"),
    (r"who\s+won\s+the\s+(?:world\s+cup|election|match|game)", "off_topic"),
    (r"write\s+a\s+poem", "off_topic"),
    (r"recipe\s+for", "off_topic"),
    (r"translate\s+(?:this\s+)?(?:sentence|text|paragraph)\s+(?:to|into)", "off_topic"),
    (r"play\s+(?:a\s+)?(?:game|quiz|trivia)", "off_topic"),
    (r"(?:recommend|suggest)\s+(?:a\s+)?(?:movie|song|restaurant|book|show)", "off_topic"),
]


def evaluate_security_and_scope(user_input: str) -> Tuple[bool, str]:
    """
    Evaluates user input against:
    1. Prompt injection / jailbreak patterns (22 patterns across 7 attack categories)
    2. Out-of-domain patterns

    Returns (is_allowed: bool, reasoning_message: str).
    Logs the matched pattern name and attack category for audit purposes.
    """
    text_lower = user_input.lower()

    # ── Check 1: Prompt Injection ─────────────────────────────────────────────
    for pattern, category in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE | re.DOTALL):
            logger.warning(
                f"[Guardrail] SECURITY VIOLATION detected! "
                f"Category='{category}', Pattern='{pattern}', "
                f"Input='{user_input[:80]}...'"
            )
            return False, (
                f"⚠️ **Security Boundary — Access Denied**\n\n"
                f"A potential **{category.replace('_', ' ')} attack** was detected in your input. "
                "This system is a Government Legal Intelligence Assistant for Law Department & LSGD officers. "
                "It is designed exclusively for building permit compliance, environmental clearance research, "
                "statutory analysis, and Form B-7 evaluation.\n\n"
                "If you believe this is a false positive, please rephrase your legal query."
            )

    # ── Check 2: Indirect injection in uploaded document content ─────────────
    # If input is very long (likely uploaded document), scan for embedded injection markers
    if len(user_input) > 500:
        injection_markers = ["ignore previous", "system prompt:", "[INST]", "<|system|>", "---new system prompt---"]
        for marker in injection_markers:
            if marker.lower() in text_lower:
                logger.warning(
                    f"[Guardrail] INDIRECT INJECTION detected in uploaded document content! "
                    f"Marker='{marker}', Input length={len(user_input)}"
                )
                return False, (
                    "⚠️ **Security Warning — Embedded Injection Detected**\n\n"
                    "The uploaded document appears to contain embedded prompt injection markers. "
                    "The document has been rejected for security reasons. "
                    "Please upload a clean, unmodified legal document."
                )

    # ── Check 3: Out-of-Domain ────────────────────────────────────────────────
    for pattern, category in OUT_OF_DOMAIN_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(
                f"[Guardrail] Out-of-domain request detected! "
                f"Category='{category}', Pattern='{pattern}', Input='{user_input[:60]}'"
            )
            return False, (
                "⚠️ **Out of Scope**\n\n"
                "I am a Government Legal Intelligence Assistant for Law & LSGD officers. "
                "I can help with:\n"
                "- Building permit compliance (Form B-7)\n"
                "- Kerala Building Rules 2022\n"
                "- Government Orders & Circulars\n"
                "- High Court of Kerala precedents\n"
                "- Environmental clearance requirements\n\n"
                "Please submit a legal query or Form B-7 application."
            )

    logger.info(f"[Guardrail] Input cleared all security checks: '{user_input[:60]}...'")
    return True, "Allowed"
