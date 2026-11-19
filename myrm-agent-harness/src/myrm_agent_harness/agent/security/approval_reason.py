"""The reason an engine decision asks the human, tagged with a stable code the approval card words in the user's language.

[INPUT]
- (none)

[OUTPUT]
- ApprovalReasonCode: the stable code of each engine decision that waits for a human answer
- CodedReason: the English reason text (for the model and the audit trail) that remembers its code and subject
- HUMAN_ONLY_CODES / is_human_only: the asks no automatic approver may settle
- is_protected_instruction_write: whether an ask is the one for a write to a protected instruction file

[POS]
The seam between the engine, which writes a reason once in English, and the cards (web, channel), which word the
same decision in the viewer's language. The code is read by whoever renders the card; the text is never parsed. The
same code tells the automatic approvers (YOLO mode, the AI security reviewer, an approval expiry) and the allowlist
which asks are not theirs to answer, and the approval stages which ask is a write to an instruction file.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypeGuard


class ApprovalReasonCode(StrEnum):
    """Why the engine pauses a call for a human answer. Values are the wire form; cards key their copy on them."""

    PATH_OUTSIDE_ZONES = "path_outside_zones"
    PATH_READ_ONLY = "path_read_only"
    PROTECTED_INSTRUCTION_WRITE = "protected_instruction_write"
    GIT_METADATA_WRITE = "git_metadata_write"
    SENSITIVE_FILE = "sensitive_file"
    DOMAIN_REQUIRES_APPROVAL = "domain_requires_approval"
    SHELL_THREAT = "shell_threat"


# The writes that decide what runs for the user later without their further say: the instruction files every session
# obeys, and the hooks and settings git runs by itself. The automatic approvers judge a call by what the model says
# about it, a page the agent just read can have written that text, and an allowlist entry answers for a call the
# user saw earlier, so a person alone answers these.
HUMAN_ONLY_CODES: frozenset[ApprovalReasonCode] = frozenset(
    {ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE, ApprovalReasonCode.GIT_METADATA_WRITE}
)


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


def is_human_only(reason: str) -> bool:
    """Whether the engine asked ``reason`` as it stands under a code in ``HUMAN_ONLY_CODES``.

    A reworded reason is a plain ``str`` with no code, so it is never human-only: the code is the engine's alone.
    """
    return isinstance(reason, CodedReason) and reason.code in HUMAN_ONLY_CODES


def is_protected_instruction_write(reason: str) -> TypeGuard[CodedReason]:
    """Whether the engine asked ``reason`` as it stands for a write to a protected instruction file.

    The same contract as ``is_human_only``: the code is read, the English text never is. A true answer also gives the
    ask's subject, the file name.
    """
    return isinstance(reason, CodedReason) and reason.code is ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE
