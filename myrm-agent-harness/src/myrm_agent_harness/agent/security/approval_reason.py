"""The reason an engine decision asks the human, tagged with a stable code the approval card words in the user's language.

[INPUT]
- (none)

[OUTPUT]
- ApprovalReasonCode: the stable code of each engine decision that waits for a human answer
- CodedReason: the English reason text (for the model and the audit trail) that remembers its code and subject

[POS]
The seam between the engine, which writes a reason once in English, and the cards (web, channel), which word the
same decision in the viewer's language. The code is read by whoever renders the card; the text is never parsed.
"""

from __future__ import annotations

from enum import StrEnum


class ApprovalReasonCode(StrEnum):
    """Why the engine pauses a call for a human answer. Values are the wire form; cards key their copy on them."""

    PATH_OUTSIDE_ZONES = "path_outside_zones"
    PATH_READ_ONLY = "path_read_only"
    PROTECTED_INSTRUCTION_WRITE = "protected_instruction_write"
    GIT_METADATA_WRITE = "git_metadata_write"
    SENSITIVE_FILE = "sensitive_file"
    DOMAIN_REQUIRES_APPROVAL = "domain_requires_approval"
    SHELL_THREAT = "shell_threat"


class CodedReason(str):
    """An engine reason that also carries which decision wrote it (``code``) and what it is about (``subject``: a path, file name or domain, or what the shell analyzer found).

    It is the text itself, so every consumer of a reason string keeps working. Any rewording of it (a prefix, an
    appended note) yields a plain ``str``, which drops the code: a card shows a code only for text the engine wrote
    as it stands.
    """

    code: ApprovalReasonCode
    subject: str

    def __new__(cls, text: str, code: ApprovalReasonCode, subject: str = "") -> CodedReason:
        reason = super().__new__(cls, text)
        reason.code = code
        reason.subject = subject
        return reason

    def __reduce__(self) -> tuple[type[CodedReason], tuple[str, ApprovalReasonCode, str]]:
        # Copying and pickling rebuild through ``__new__``, which needs the code and the subject as well as the text.
        return type(self), (str(self), self.code, self.subject)
