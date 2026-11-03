"""The imap-smtp-email skill works from the copy the seed sync writes for a user, not only from the source tree.

The script imports its sibling package ``mail_client``, which ships without ``__init__.py`` because the seed sync leaves
out every path that has an underscore-prefixed part. A change to those sync rules, or to the package's name, would hand a
user a script that fails on import, and no test of the source tree would notice. This test syncs the real prebuilt seeds
into a temporary storage, checks that the script and each module of the package arrive unchanged, and runs the synced
script against a loopback IMAP server whose answers carry the headers as literals, the way a real server sends them.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email: the bundle that is synced and run
- app/core/skills/prebuilt_sync.py: the seed sync under test
- tests/support/email_skill_script.py: the loopback listener and the script runner
- tests/assets/conftest.py: the loopback certificate

[OUTPUT]
- Fails when the synced bundle lacks the script or a module of ``mail_client`` or differs from the source, or when the
  synced script cannot list the messages of a server that sends their headers as literals

[POS]
Packaging test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py``, which runs the source tree's
copy; among the tests of the script, only this one has ``check`` read headers from a real imaplib literal answer (the
others use a double or an empty mailbox).
"""

from __future__ import annotations

import json
import socket
import ssl
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.storage.paths import get_skill_file_path
from app.core.storage.types import SkillType
from tests.support.email_skill_script import SKILL_SCRIPTS, run_email_script, serve_sessions

_SKILL_ID = "imap-smtp-email"
_SOURCE = SKILL_SCRIPTS.parent
_BUNDLE = (
    "scripts/email_manager.py",
    "scripts/mail_client/attachments.py",
    "scripts/mail_client/message.py",
    "scripts/mail_client/transport.py",
)
_HEADERS = {
    1: b"From: Alice <alice@example.test>\r\nTo: me@example.test\r\nSubject: Quarterly report\r\n"
    b"Date: Mon, 02 Nov 2026 09:00:00 +0000\r\nMessage-ID: <1@example.test>\r\n\r\n",
    2: b"From: =?utf-8?b?5byg5LiJ?= <zhang@example.test>\r\nSubject: =?utf-8?b?5Y+R56Wo?=\r\n"
    b"Date: Tue, 03 Nov 2026 08:00:00 +0000\r\nMessage-ID: <2@example.test>\r\n\r\n",
}


class _Inbox:
    """A logged-in IMAP server holding the messages of ``_HEADERS``; it records every command line it is sent, tags removed."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def session(self, conn: socket.socket, context: ssl.SSLContext) -> None:
        with context.wrap_socket(conn, server_side=True) as tls, tls.makefile("rwb") as stream:
            stream.write(b"* OK IMAP4rev1 ready\r\n")
            stream.flush()
            for raw in stream:
                tag, _, command = raw.decode().rstrip("\r\n").partition(" ")
                if command.split(" ", 1)[0].upper() not in {"CAPABILITY", "ID", "LOGIN", "LOGOUT"}:
                    self.commands.append(command)
                stream.write(self._reply(tag, command))
                stream.flush()

    @staticmethod
    def _reply(tag: str, command: str) -> bytes:
        words = command.upper().split()
        match words[:2]:
            case ["CAPABILITY", *_]:
                return f"* CAPABILITY IMAP4rev1\r\n{tag} OK done\r\n".encode()
            case ["EXAMINE" | "SELECT", *_]:
                return f"* {len(_HEADERS)} EXISTS\r\n{tag} OK [READ-ONLY] done\r\n".encode()
            case ["UID", "SEARCH"]:
                return f"* SEARCH {' '.join(map(str, _HEADERS))}\r\n{tag} OK done\r\n".encode()
            case ["UID", "FETCH"]:
                uid = int(command.split()[2])
                headers = _HEADERS[uid]
                literal = f"* {uid} FETCH (UID {uid} RFC822.HEADER {{{len(headers)}}}\r\n".encode()
                return literal + headers + f")\r\n{tag} OK done\r\n".encode()
            case ["LOGOUT", *_]:
                return f"* BYE\r\n{tag} OK done\r\n".encode()
            case _:
                return f"{tag} OK done\r\n".encode()


@pytest.fixture
async def seeded_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory the seed sync writes the skill to; the sync runs once per process unless this flag is cleared."""
    monkeypatch.setattr(prebuilt_sync, "_synced", False)
    storage = LocalStorageBackend(str(tmp_path / "storage"))
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert _SKILL_ID in result.skill_ids
    return (storage.base_path / get_skill_file_path(SkillType.PREBUILT, _SKILL_ID, _BUNDLE[0])).parents[1]


@pytest.mark.parametrize("relative", _BUNDLE)
def test_the_synced_skill_holds_the_script_and_every_module_of_its_package_unchanged(seeded_skill: Path, relative: str) -> None:
    assert (seeded_skill / relative).read_bytes() == (_SOURCE / relative).read_bytes()


def test_the_synced_script_lists_the_messages_of_a_server_that_sends_headers_as_literals(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], seeded_skill: Path
) -> None:
    inbox = _Inbox()

    with serve_sessions(inbox.session, listener_tls[0]) as port:
        proc = run_email_script(
            tmp_path, ["check", "--limit", "5"], port=port, trust=listener_tls[1], script=seeded_skill / _BUNDLE[0]
        )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {
        "messages": [
            {
                "uid": 2,
                "from": "张三 <zhang@example.test>",
                "to": "",
                "subject": "发票",
                "date": "2026-11-03T08:00:00+00:00",
                "message_id": "<2@example.test>",
            },
            {
                "uid": 1,
                "from": "Alice <alice@example.test>",
                "to": "me@example.test",
                "subject": "Quarterly report",
                "date": "2026-11-02T09:00:00+00:00",
                "message_id": "<1@example.test>",
            },
        ],
        "total": 2,
    }
    assert inbox.commands == ["EXAMINE INBOX", "UID SEARCH (ALL)", "UID FETCH 2 (RFC822.HEADER)", "UID FETCH 1 (RFC822.HEADER)"]
