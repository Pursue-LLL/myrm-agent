#!/usr/bin/env python3
"""Standard sandbox execution script for x-live-search skill (PTC pattern).

[INPUT]
- Process env XAI_API_KEY (injected by LocalExecutor/safe_exec from session credentials)
- Optional process env XAI_BASE_URL (defaults to https://api.x.ai/v1)

[OUTPUT]
- Structured text + Markdown source citations on stdout
- Exit code 0 on success, non-zero on error

[POS]
Vendor-decoupled sandbox script for x-live-search prebuilt skill.
Executed via bash_code_execute_tool (PTC mode) in agent sandbox.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

_DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-3"
_MAX_HANDLES = 10
_MAX_RETRIES = 2
_ALLOWED_HOSTS = frozenset({"api.x.ai"})


def _normalize_handles(raw_handles: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for h in raw_handles or []:
        norm = str(h or "").strip().lstrip("@")
        if norm:
            cleaned.append(norm)
    if len(cleaned) > _MAX_HANDLES:
        raise ValueError(f"Maximum {_MAX_HANDLES} handles allowed (got {len(cleaned)})")
    return cleaned


def _validate_date_range(from_date: str, to_date: str) -> str | None:
    parsed_from: date | None = None
    parsed_to: date | None = None
    for raw, label in ((from_date, "from_date"), (to_date, "to_date")):
        trimmed = raw.strip()
        if not trimmed:
            continue
        try:
            parsed = datetime.strptime(trimmed, "%Y-%m-%d").date()
        except ValueError:
            return f"{label} must be YYYY-MM-DD (got {trimmed!r})"
        if label == "from_date":
            parsed_from = parsed
        else:
            parsed_to = parsed
    if parsed_from and parsed_to and parsed_from > parsed_to:
        return f"from_date ({parsed_from.isoformat()}) must be on or before to_date ({parsed_to.isoformat()})"
    if parsed_from is not None and parsed_from > datetime.now(timezone.utc).date():
        return f"from_date ({parsed_from.isoformat()}) is in the future; X Search only indexes past posts"
    return None


def _validate_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url.strip())
    hostname = (parsed.hostname or "").strip().lower()
    if parsed.scheme != "https" or hostname not in _ALLOWED_HOSTS:
        return _DEFAULT_XAI_BASE_URL
    return base_url.rstrip("/")


def _extract_response_text(payload: dict[str, object]) -> str:
    output_text = str(payload.get("output_text") or "").strip()
    if output_text:
        return output_text

    parts: list[str] = []
    output_items = payload.get("output")
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            contents = item.get("content")
            if isinstance(contents, list):
                for content in contents:
                    if not isinstance(content, dict):
                        continue
                    if content.get("type") in ("output_text", "text"):
                        text = str(content.get("text") or "").strip()
                        if text:
                            parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_inline_citations(payload: dict[str, object]) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    output_items = payload.get("output")
    if isinstance(output_items, list):
        for item in output_items:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            contents = item.get("content")
            if isinstance(contents, list):
                for content in contents:
                    if not isinstance(content, dict):
                        continue
                    annotations = content.get("annotations")
                    if isinstance(annotations, list):
                        for ann in annotations:
                            if isinstance(ann, dict) and ann.get("type") == "url_citation":
                                citations.append(
                                    {
                                        "url": str(ann.get("url", "")),
                                        "title": str(ann.get("title", "")),
                                    }
                                )
    return citations


def execute_search(
    query: str,
    *,
    allowed_handles: list[str] | None = None,
    excluded_handles: list[str] | None = None,
    from_date: str = "",
    to_date: str = "",
    enable_image_understanding: bool = False,
    enable_video_understanding: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
) -> int:
    resolved_key = (api_key or os.environ.get("XAI_API_KEY", "")).strip()
    if not resolved_key:
        print(
            "Error: xAI credentials not configured.\n"
            "Add an xAI provider in Settings → Models & Providers, "
            "or connect your SuperGrok token in Settings → Integrations → Credentials.",
            file=sys.stderr,
        )
        return 1

    try:
        allowed = _normalize_handles(allowed_handles)
        excluded = _normalize_handles(excluded_handles)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if allowed and excluded:
        print("Error: allowed_handles and excluded_handles cannot be used together", file=sys.stderr)
        return 1

    date_error = _validate_date_range(from_date, to_date)
    if date_error:
        print(f"Error: {date_error}", file=sys.stderr)
        return 1

    raw_base = (base_url or os.environ.get("XAI_BASE_URL", _DEFAULT_XAI_BASE_URL)).strip()
    resolved_base = _validate_base_url(raw_base)

    tool_def: dict[str, object] = {"type": "x_search"}
    if allowed:
        tool_def["allowed_x_handles"] = allowed
    if excluded:
        tool_def["excluded_x_handles"] = excluded
    if from_date.strip():
        tool_def["from_date"] = from_date.strip()
    if to_date.strip():
        tool_def["to_date"] = to_date.strip()
    if enable_image_understanding:
        tool_def["enable_image_understanding"] = True
    if enable_video_understanding:
        tool_def["enable_video_understanding"] = True

    payload = {
        "model": _DEFAULT_MODEL,
        "input": [{"role": "user", "content": query.strip()}],
        "tools": [tool_def],
        "store": False,
    }

    url = f"{resolved_base}/responses"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
            "User-Agent": "MyrmAgent-PTC/1.0",
        },
        method="POST",
    )

    last_error: str | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                body = response.read().decode("utf-8")
                res_data = json.loads(body)
                answer = _extract_response_text(res_data)
                inline_citations = _extract_inline_citations(res_data)
                top_citations = res_data.get("citations") or []

                seen_urls: set[str] = set()
                merged_sources: list[tuple[str, str]] = []
                for item in inline_citations:
                    u = str(item.get("url") or "")
                    t = str(item.get("title") or "")
                    if u and u not in seen_urls:
                        seen_urls.add(u)
                        merged_sources.append((t or u, u))

                if isinstance(top_citations, list):
                    for tc in top_citations:
                        u = tc.get("url", "") if isinstance(tc, dict) else str(tc)
                        t = tc.get("title", "") if isinstance(tc, dict) else ""
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            merged_sources.append((t or u, u))

                has_filters = bool(allowed or excluded or from_date.strip() or to_date.strip())
                if has_filters and not merged_sources:
                    answer += (
                        "\n\nNote: No matching posts found for the specified filters. "
                        "This answer may be based on general knowledge rather than actual X posts."
                    )

                print(answer)
                if merged_sources:
                    print("\nSources:")
                    for title, link in merged_sources:
                        print(f"- [{title}]({link})")
                return 0
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code < 500 or attempt >= _MAX_RETRIES:
                break
            time.sleep(min(3.0, 1.0 * (attempt + 1)))
        except urllib.error.URLError as exc:
            last_error = f"Network error: {exc.reason}"
            if attempt >= _MAX_RETRIES:
                break
            time.sleep(min(3.0, 1.0 * (attempt + 1)))
        except Exception as exc:
            last_error = f"Execution error: {exc}"
            break

    print(f"Error executing X search: {last_error}", file=sys.stderr)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Search X (Twitter) via xAI Live Search API.")
    parser.add_argument("--query", "-q", required=True, help="Search query")
    parser.add_argument("--handles", nargs="*", default=None, help="Include only these handles (max 10)")
    parser.add_argument("--exclude-handles", nargs="*", default=None, help="Exclude these handles (max 10)")
    parser.add_argument("--from-date", default="", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", default="", help="End date (YYYY-MM-DD)")
    parser.add_argument("--image-understanding", action="store_true", help="Enable image analysis")
    parser.add_argument("--video-understanding", action="store_true", help="Enable video analysis")

    args = parser.parse_args()
    code = execute_search(
        query=args.query,
        allowed_handles=args.handles,
        excluded_handles=args.exclude_handles,
        from_date=args.from_date,
        to_date=args.to_date,
        enable_image_understanding=args.image_understanding,
        enable_video_understanding=args.video_understanding,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
