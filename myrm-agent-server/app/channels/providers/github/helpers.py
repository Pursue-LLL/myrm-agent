"""GitHub helpers — signature verification and API client.

[INPUT]
(no external channel dependencies)

[OUTPUT]
- verify_github_signature: X-Hub-Signature-256 HMAC verification
- post_issue_comment: Post a comment to a GitHub issue/PR via REST API

[POS]
Pure-function signature verification and minimal GitHub REST API client
for outbound comment delivery.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_TIMEOUT = 15.0


def verify_github_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Verify GitHub webhook signature using X-Hub-Signature-256.

    GitHub sends: sha256=<hex-digest>
    We compute HMAC-SHA256(secret, body) and compare.
    """
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[7:]
    computed = hmac.HMAC(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected)


async def post_issue_comment(
    token: str,
    repo: str,
    issue_number: int,
    body: str,
) -> bool:
    """Post a comment to a GitHub issue or pull request.

    Returns True on success, False on failure.
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
            if resp.status_code == 201:
                return True
            logger.warning(
                "GitHub API comment failed: %d %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except httpx.HTTPError as exc:
        logger.error("GitHub API request error: %s", exc)
        return False
