"""What a credential the vault filled leaves behind: wherever the session would show it, it is redacted.

[INPUT]
- dref.types::ElementRef (POS: the element whose value a capture reports)

[OUTPUT]
- REDACTED: what replaces a secret in a value or a message
- FilledSecrets: the secrets the vault filled into controls of the session; redacts text and masks a capture by them

[POS]
A credential filled into a control stays in that control, and the accessibility tree reports it as the control's
value, so the model would read it back in the next snapshot. Typing does not always replace what the control held
(a retried fill, or text typed at the caret), so the secret is replaced wherever it occurs in a value, not only
when it is the whole value. The session masks a capture before the registry adopts it, so the follow-up snapshot, a
later snapshot, the registry, the diff and the inspector all carry the redaction, and it redacts the backend errors a
reply quotes. The secrets are the vault's own strings, held for the life of the session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef

REDACTED = "[REDACTED]"


class FilledSecrets:
    """The secrets the vault filled into controls of one session."""

    def __init__(self) -> None:
        # Longest first, so a secret that contains another one is replaced whole.
        self._secrets: tuple[str, ...] = ()

    def remember(self, secret: str) -> None:
        """Redact `secret` from now on; an empty secret redacts nothing."""
        if secret and secret not in self._secrets:
            self._secrets = tuple(sorted((*self._secrets, secret), key=len, reverse=True))

    def redact(self, text: str) -> str:
        """`text` with every occurrence of a remembered secret replaced."""
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def mask(self, capture: Mapping[str, ElementRef]) -> dict[str, ElementRef]:
        """The capture with the secrets redacted from every control value."""
        if not self._secrets:
            return dict(capture)
        masked: dict[str, ElementRef] = {}
        for ref_id, element in capture.items():
            value = self.redact(element.value)
            masked[ref_id] = element if value == element.value else replace(element, value=value)
        return masked
