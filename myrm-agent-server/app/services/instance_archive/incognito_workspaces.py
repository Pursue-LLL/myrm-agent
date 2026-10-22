"""The workspace files of web incognito chats, kept out of every export.

[INPUT]
- app.platform_utils.workspace_session::CHAT_SESSION_PREFIX (POS: how a chat id becomes its workspace directory name)
- app.services.instance_archive.policy::StateScan (POS: the export's file list)

[OUTPUT]
- WORKSPACES_REL: where the per-chat workspaces sit below the state directory
- without_incognito_workspaces: the scan minus everything under the workspaces of the given chats

[POS]
Tools are not gated in an incognito chat: the agent writes files into the chat's workspace
(``harness/workspaces/chat_<id>/``, its artifact vault included) like in any other chat, and nothing but the chat
row names that directory. Once the chat rows are scrubbed from the archive, those files would be orphans that
still carry what the chat produced. The chats come from the live database, so the choice is made per export and
a chat that became incognito after an earlier backup is covered by the next one.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.platform_utils.workspace_session import CHAT_SESSION_PREFIX
from app.services.instance_archive.policy import StateScan

WORKSPACES_REL = ("harness", "workspaces")


def without_incognito_workspaces(scan: StateScan, chat_ids: Sequence[str]) -> StateScan:
    """``scan`` without the files, and without the unreadable paths, under the workspaces of ``chat_ids``.

    Unreadable paths go too: they are left out on purpose, so they must not make the archive look incomplete.
    Directory names are compared as whole path components; ``chat_a`` never hides ``chat_ab``.
    """
    if not chat_ids:
        return scan
    names = frozenset(f"{CHAT_SESSION_PREFIX}{chat_id}" for chat_id in chat_ids)
    depth = len(WORKSPACES_REL)

    def inside_incognito_workspace(rel: str) -> bool:
        parts = rel.split("/")
        return len(parts) > depth and tuple(parts[:depth]) == WORKSPACES_REL and parts[depth] in names

    return StateScan(
        sources=[source for source in scan.sources if not inside_incognito_workspace(source.rel)],
        excluded=scan.excluded,
        unreadable=[rel for rel in scan.unreadable if not inside_incognito_workspace(rel)],
    )
