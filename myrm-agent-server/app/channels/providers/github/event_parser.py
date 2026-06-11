"""GitHub Webhook event parser — structured semantic extraction.

Transforms raw GitHub webhook payloads into human-readable markdown context
that enables the Agent to understand and respond to GitHub events effectively.

[INPUT]
- Raw GitHub webhook event payloads (dict)

[OUTPUT]
- parse_github_event: extracts structured context from webhook payload
- GitHubEventContext: typed container for parsed event data

[POS]
Stateless event parsing. Converts raw webhook JSON into structured InboundMessage
content with rich markdown context for Agent comprehension.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GitHubEventContext:
    """Parsed GitHub event with structured fields for Agent context."""

    event_type: str
    action: str
    repo_full_name: str
    sender: str
    title: str
    body: str
    url: str
    number: int | None = None
    labels: tuple[str, ...] = ()
    ref: str = ""


def parse_github_event(event_type: str, payload: dict[str, Any]) -> GitHubEventContext | None:
    """Parse a GitHub webhook payload into structured context.

    Returns None for unsupported or malformed events.
    """
    action = str(payload.get("action", ""))
    repo = payload.get("repository", {})
    repo_full_name = str(repo.get("full_name", "")) if isinstance(repo, dict) else ""
    sender_obj = payload.get("sender", {})
    sender = str(sender_obj.get("login", "")) if isinstance(sender_obj, dict) else ""

    if event_type == "issues":
        return _parse_issue_event(action, payload, repo_full_name, sender)
    if event_type == "pull_request":
        return _parse_pr_event(action, payload, repo_full_name, sender)
    if event_type == "issue_comment":
        return _parse_comment_event(action, payload, repo_full_name, sender)
    if event_type == "push":
        return _parse_push_event(payload, repo_full_name, sender)
    if event_type == "pull_request_review":
        return _parse_review_event(action, payload, repo_full_name, sender)

    return None


def format_event_as_markdown(ctx: GitHubEventContext) -> str:
    """Render parsed event context as markdown for Agent consumption."""
    lines: list[str] = []
    lines.append(f"## GitHub: {ctx.event_type} ({ctx.action})")
    lines.append(f"**Repo**: {ctx.repo_full_name}")
    lines.append(f"**By**: @{ctx.sender}")

    if ctx.number is not None:
        lines.append(f"**#{ctx.number}**: [{ctx.title}]({ctx.url})")
    elif ctx.title:
        lines.append(f"**Title**: {ctx.title}")

    if ctx.labels:
        lines.append(f"**Labels**: {', '.join(ctx.labels)}")

    if ctx.ref:
        lines.append(f"**Ref**: `{ctx.ref}`")

    if ctx.body:
        lines.append("")
        body_preview = ctx.body[:2000]
        if len(ctx.body) > 2000:
            body_preview += "\n\n_(truncated)_"
        lines.append(body_preview)

    return "\n".join(lines)


# -- Private parsers ---------------------------------------------------------


def _parse_issue_event(
    action: str,
    payload: dict[str, Any],
    repo: str,
    sender: str,
) -> GitHubEventContext | None:
    issue = payload.get("issue", {})
    if not isinstance(issue, dict):
        return None
    return GitHubEventContext(
        event_type="issue",
        action=action,
        repo_full_name=repo,
        sender=sender,
        title=str(issue.get("title", "")),
        body=str(issue.get("body", "") or ""),
        url=str(issue.get("html_url", "")),
        number=int(issue["number"]) if "number" in issue else None,
        labels=tuple(
            str(lbl.get("name", ""))
            for lbl in issue.get("labels", [])
            if isinstance(lbl, dict)
        ),
    )


def _parse_pr_event(
    action: str,
    payload: dict[str, Any],
    repo: str,
    sender: str,
) -> GitHubEventContext | None:
    pr = payload.get("pull_request", {})
    if not isinstance(pr, dict):
        return None
    return GitHubEventContext(
        event_type="pull_request",
        action=action,
        repo_full_name=repo,
        sender=sender,
        title=str(pr.get("title", "")),
        body=str(pr.get("body", "") or ""),
        url=str(pr.get("html_url", "")),
        number=int(pr["number"]) if "number" in pr else None,
        labels=tuple(
            str(lbl.get("name", ""))
            for lbl in pr.get("labels", [])
            if isinstance(lbl, dict)
        ),
        ref=str(pr.get("head", {}).get("ref", "")),
    )


def _parse_comment_event(
    action: str,
    payload: dict[str, Any],
    repo: str,
    sender: str,
) -> GitHubEventContext | None:
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    if not isinstance(comment, dict) or not isinstance(issue, dict):
        return None
    return GitHubEventContext(
        event_type="issue_comment",
        action=action,
        repo_full_name=repo,
        sender=sender,
        title=str(issue.get("title", "")),
        body=str(comment.get("body", "") or ""),
        url=str(comment.get("html_url", "")),
        number=int(issue["number"]) if "number" in issue else None,
    )


def _parse_push_event(
    payload: dict[str, Any],
    repo: str,
    sender: str,
) -> GitHubEventContext | None:
    commits = payload.get("commits", [])
    if not isinstance(commits, list):
        return None
    ref = str(payload.get("ref", ""))
    commit_msgs = [
        str(c.get("message", "")).split("\n")[0]
        for c in commits[:10]
        if isinstance(c, dict)
    ]
    body = "\n".join(f"- {msg}" for msg in commit_msgs) if commit_msgs else ""
    return GitHubEventContext(
        event_type="push",
        action="pushed",
        repo_full_name=repo,
        sender=sender,
        title=f"{len(commits)} commit(s) to {ref.split('/')[-1]}",
        body=body,
        url=str(payload.get("compare", "")),
        ref=ref,
    )


def _parse_review_event(
    action: str,
    payload: dict[str, Any],
    repo: str,
    sender: str,
) -> GitHubEventContext | None:
    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    if not isinstance(review, dict) or not isinstance(pr, dict):
        return None
    state = str(review.get("state", ""))
    return GitHubEventContext(
        event_type="pull_request_review",
        action=f"{action} ({state})",
        repo_full_name=repo,
        sender=sender,
        title=str(pr.get("title", "")),
        body=str(review.get("body", "") or ""),
        url=str(review.get("html_url", "")),
        number=int(pr["number"]) if "number" in pr else None,
    )
