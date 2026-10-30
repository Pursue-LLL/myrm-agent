"""Phase 2 helpers of the evolution screener: the signals of a failure log, the confirmation prompt, the answer.

[INPUT]
- utils.json_parsing::parse_llm_json_object (POS: robust JSON object extraction from LLM output — fences, prose, bare control chars, trailing commas)

[OUTPUT]
- extract_error_signals: HTTP status codes, exception types and error keywords found in a failure log
- build_confirmation_prompt: The prompt that asks the cheap model whether a failure is a skill defect
- parse_confirmation_response: The cheap model's answer as (decision, reason, confidence)

[POS]
Pure text functions behind the screener's static interception and LLM confirmation; no state, no I/O.
"""

from __future__ import annotations

import re

from myrm_agent_harness.utils.json_parsing import parse_llm_json_object

__all__ = ["build_confirmation_prompt", "extract_error_signals", "parse_confirmation_response"]


def extract_error_signals(error_log: str) -> dict[str, str]:
    """Extract key error signals from log.

    Extracts:
    - HTTP status codes (404, 500, etc.)
    - Exception types (ValueError, KeyError, etc.)
    - Error keywords (timeout, connection, permission, etc.)

    Args:
        error_log: Raw error log

    Returns:
        Dict with extracted signals
    """
    signals: dict[str, str] = {}

    # Extract HTTP status codes
    http_pattern = r"\b((?:HTTP\s*)?[1-5]\d{2})\b"
    http_matches = re.findall(http_pattern, error_log, re.IGNORECASE)
    if http_matches:
        signals["http_status"] = ", ".join(set(http_matches))

    # Extract exception types
    exception_pattern = r"\b(\w+(?:Error|Exception))\b"
    exception_matches = re.findall(exception_pattern, error_log)
    if exception_matches:
        signals["exception_types"] = ", ".join(set(exception_matches[:3]))  # Top 3

    # Extract error keywords
    error_keywords = [
        "timeout",
        "connection",
        "permission",
        "denied",
        "forbidden",
        "not found",
        "unauthorized",
        "rate limit",
        "quota",
        "unavailable",
    ]
    found_keywords = [kw for kw in error_keywords if kw.lower() in error_log.lower()]
    if found_keywords:
        signals["error_keywords"] = ", ".join(found_keywords[:3])

    return signals


def build_confirmation_prompt(skill_content: str, error_log: str, error_signals: dict[str, str]) -> str:
    """Build optimized prompt for LLM confirmation.

    Key optimizations:
    - Extract error signals upfront (HTTP status, exception type)
    - Truncate skill content to first 2000 chars (signatures only)
    - Clear decision criteria (skill defect vs external/usage error)

    Args:
        skill_content: Current skill content
        error_log: Error log or feedback
        error_signals: Extracted error signals

    Returns:
        Optimized prompt string
    """
    # Build signals summary
    signals_text = ""
    if error_signals:
        signals_parts = []
        if "http_status" in error_signals:
            signals_parts.append(f"HTTP Status: {error_signals['http_status']}")
        if "exception_types" in error_signals:
            signals_parts.append(f"Exceptions: {error_signals['exception_types']}")
        if "error_keywords" in error_signals:
            signals_parts.append(f"Keywords: {error_signals['error_keywords']}")
        if signals_parts:
            signals_text = "\n\nError Signals:\n" + "\n".join(f"- {p}" for p in signals_parts)

    return f"""Analyze if the skill code has a real defect that requires modification.

Error Log:
{error_log[:1000]}{signals_text}

Skill Code (first 2000 chars):
{skill_content[:2000]}

Decision Criteria:
- CONFIRM (YES) if: Skill logic is incorrect, outdated API usage, missing error handling, or syntax error
- REJECT (NO) if: External service error (404, 500, timeout), user input error, API rate limit, or network issue

Please answer YES or NO, then explain your reasoning in one sentence.

Answer:"""


def parse_confirmation_response(content: str) -> tuple[bool, str, float]:
    """Parse LLM confirmation response.

    Supports multiple formats:
    - "YES" / "NO" at start
    - "CONFIRMED" / "REJECTED"
    - Structured JSON with decision + reason + confidence

    Args:
        content: LLM response content

    Returns:
        Tuple of (decision: bool, reason: str, confidence: float)
    """
    stripped = content.strip()
    content_upper = stripped.upper()

    # Format 0: Structured JSON
    if stripped.startswith("{"):
        data = parse_llm_json_object(stripped)
        if data is not None:
            try:
                approved = bool(data.get("approved", data.get("decision", False)))
                reason = str(data.get("reason", stripped))
                confidence = float(str(data.get("confidence", 0.8)))
                return approved, reason, confidence
            except (ValueError, TypeError):
                pass

    # Format 1: Simple YES/NO
    if content_upper.startswith("YES"):
        return True, content.strip(), 0.8
    if content_upper.startswith("NO"):
        return False, content.strip(), 0.8

    # Format 2: CONFIRMED/REJECTED
    if "CONFIRMED" in content_upper:
        return True, content.strip(), 0.8
    if "REJECTED" in content_upper:
        return False, content.strip(), 0.8

    # Format 3: Try to parse confidence from text
    confidence = 0.5  # Default
    confidence_pattern = r"confidence[:\s]+([0-9.]+)"
    confidence_match = re.search(confidence_pattern, content, re.IGNORECASE)
    if confidence_match:
        try:
            confidence = float(confidence_match.group(1))
            if confidence > 1.0:  # Handle percentage format
                confidence = confidence / 100.0
        except ValueError:
            pass

    # Fallback: analyze sentiment
    negative_keywords = [
        "not a defect",
        "not a bug",
        "not the skill",
        "external",
        "api",
        "service",
    ]
    if any(kw in content.lower() for kw in negative_keywords):
        return False, content.strip(), confidence

    # Default: allow if unclear
    return True, content.strip(), 0.5
