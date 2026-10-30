"""Unit tests: the page-side attach probe of the skill-hooks Chrome lane does not report a chat ready while its own attach runs.

The bridge's attach ends by re-creating the chat view, the composer in it included. A probe that answers ready as soon as the
store holds the chat lets the test type into a composer that is replaced a moment later (caret and focus lost, no slash palette).
The scripts are plain JavaScript, so they run here in Node against a fake ``window``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from tests.support.chrome_skill_hooks_slash_js import ATTACH_CHAT_PROBE

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the page scripts are run with Node")

_CHAT_ID = "e2ehooks-chat"

# Three polls of the probe: before anything, while the attach it started is still running (the store may have loaded the chat
# by then), and after that attach ended.
_HARNESS = """
const vm = require('node:vm');
const scenario = JSON.parse(process.env.SCENARIO);
const store = { ...scenario.store };
let attachCalls = 0;
let endAttach;
const window = {
  __myrmChatStore: { getState: () => store },
  addEventListener: () => {},
  __MYRM_E2E_CHAT__: {
    attachToChat: () => {
      attachCalls += 1;
      return new Promise((resolve) => { endAttach = resolve; });
    },
  },
};
const context = vm.createContext({ window, performance });
const poll = () => vm.runInContext(process.env.PROBE, context);
(async () => {
  const before = poll();
  Object.assign(store, scenario.storeWhileAttaching);
  const during = poll();
  const attachCallsWhileAttaching = attachCalls;
  if (endAttach) endAttach();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const after = poll();
  console.log(JSON.stringify({ before, during, after, attachCalls, attachCallsWhileAttaching }));
})();
"""

_HOLDS_THE_CHAT: Mapping[str, object] = {"chatId": _CHAT_ID, "isMessagesLoaded": True, "loadError": False, "notFound": False}
_EMPTY: Mapping[str, object] = {"chatId": None, "isMessagesLoaded": False, "loadError": False, "notFound": False}


@dataclass(frozen=True)
class _ProbeRun:
    before: dict[str, object]
    during: dict[str, object]
    after: dict[str, object]
    attach_calls: int
    attach_calls_while_attaching: int


def _run(*, store: Mapping[str, object], store_while_attaching: Mapping[str, object]) -> _ProbeRun:
    scenario = {"store": store, "storeWhileAttaching": store_while_attaching}
    probe = ATTACH_CHAT_PROBE.format(chat_id_json=json.dumps(_CHAT_ID))
    completed = subprocess.run(
        [shutil.which("node") or "node", "-e", _HARNESS],
        env={**os.environ, "SCENARIO": json.dumps(scenario), "PROBE": probe},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    reported = json.loads(completed.stdout)
    return _ProbeRun(
        before=reported["before"],
        during=reported["during"],
        after=reported["after"],
        attach_calls=reported["attachCalls"],
        attach_calls_while_attaching=reported["attachCallsWhileAttaching"],
    )


def test_a_page_whose_store_loads_the_chat_during_the_attach_is_not_ready_until_the_attach_ends() -> None:
    run = _run(store=_EMPTY, store_while_attaching=_HOLDS_THE_CHAT)

    assert run.before["ready"] is False
    assert run.during["ready"] is False
    assert run.during["attaching"] is True
    assert run.after == {"ready": True, "chatId": _CHAT_ID}


def test_one_attach_serves_every_poll_until_it_ends_and_an_attach_that_ends_without_the_chat_is_retried() -> None:
    run = _run(store=_EMPTY, store_while_attaching=_EMPTY)

    assert run.attach_calls_while_attaching == 1
    assert run.after["ready"] is False
    assert run.attach_calls == 2


def test_a_page_whose_store_already_holds_the_chat_is_ready_without_an_attach() -> None:
    run = _run(store=_HOLDS_THE_CHAT, store_while_attaching=_HOLDS_THE_CHAT)

    assert run.before == {"ready": True, "chatId": _CHAT_ID}
    assert run.attach_calls == 0
