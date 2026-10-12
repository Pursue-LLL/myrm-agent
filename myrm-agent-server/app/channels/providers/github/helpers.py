"""GitHub helpers — REST API client.

[INPUT]
- channels.core.exceptions::ChannelSendError (POS: Channel exception hierarchy for precise retry and error handling.)

[OUTPUT]
- post_issue_comment: Post a comment to a GitHub issue/PR via REST API; raises ChannelSendError when GitHub does not accept it

[POS]
Minimal GitHub REST API client for outbound comment delivery.
"""

from __future__ import annotations

import httpx

from app.channels.core.exceptions import ChannelSendError

_API_BASE = "https://api.github.com"
_TIMEOUT = 15.0


async def post_issue_comment(
    token: str,
    repo: str,
    issue_number: int,
    body: str,
) -> None:
    """Post a comment to a GitHub issue or pull request.

    Raises ``ChannelSendError`` unless GitHub accepted the comment.
    """
    url = f"{_API_BASE}/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"body": body}, headers=headers)
    except httpx.HTTPError as exc:
        raise ChannelSendError(f"GitHub API request failed: {exc}", channel="github") from exc
    if resp.status_code != 201:
        raise ChannelSendError.from_http_status("github", resp.status_code, resp.text)
