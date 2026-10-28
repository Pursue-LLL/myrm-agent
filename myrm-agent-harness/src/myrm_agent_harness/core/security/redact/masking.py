"""Value masking of the runtime redactor.

A masked secret tells the reader which credential it was without disclosing it. A machine-issued token keeps its head
and tail, since the head names the issuer (``sk-ant-``, ``ghp_``) and the rest is random. A password or passphrase is a
phrase a person chose, and its head and tail (``correc...aple``) disclose most of it, so it is hidden completely.

[INPUT]
- (none — pure helper definitions)

[OUTPUT]
- ``_mask_token`` — mask a bare token: short ones completely, long ones keep head and tail
- ``_mask_secret`` — mask the value of the credential called ``name``; a password or passphrase is always completely hidden

[POS]
Leaf value-masking helpers of the runtime redactor; shared by ``patterns.py``, ``structured_fields.py`` and ``engine.py``.
"""

from __future__ import annotations

import re

# A substring match on purpose: a name that merely contains ``pass`` or ``pw`` (``bypass_token``) is hidden completely
# too, which errs on the side of showing less.
_HUMAN_SECRET_NAME_RE = re.compile(r"pass|pw", re.IGNORECASE)


def _mask_token(token: str) -> str:
    """Mask a token: fully hide short ones, preserve head/tail for long ones."""
    if len(token) < 18:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def _mask_secret(name: str, value: str) -> str:
    """Mask ``value`` of the credential called ``name``; a password or passphrase is always completely hidden."""
    if _HUMAN_SECRET_NAME_RE.search(name):
        return "***"
    return _mask_token(value)
