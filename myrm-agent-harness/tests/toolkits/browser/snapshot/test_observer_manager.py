"""Observer self-healing: which page-side states make a cached snapshot untrustworthy.

[INPUT]
- snapshot.observer_manager::ObserverManager (POS: installs and re-anchors the in-page MutationObserver)
- snapshot.observer_scripts::MUTATION_OBSERVER_SCRIPT (POS: the script that installs the observer)

[OUTPUT]
- one test per answer the page can give to "is the observer watching the live body?"

[POS]
Unit proof with a scripted frame; the same behaviour against a real Chromium navigation is in
`test_snapshot_after_navigation_integration.py`.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.browser.snapshot.observer_manager import ObserverManager
from myrm_agent_harness.toolkits.browser.snapshot.observer_scripts import MUTATION_OBSERVER_SCRIPT


class _ScriptedFrame:
    """A frame whose page answers each `ensureActive` probe from a script and counts observer installs."""

    def __init__(self, *answers: object, install_fails: bool = False) -> None:
        self._answers = list(answers)
        self._install_fails = install_fails
        self.installs = 0

    async def evaluate(self, script: str) -> object:
        if script == MUTATION_OBSERVER_SCRIPT:
            if self._install_fails:
                raise RuntimeError("document has no body")
            self.installs += 1
            return None
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


async def _installed(frame: _ScriptedFrame) -> ObserverManager:
    observer = ObserverManager(frame)  # type: ignore[arg-type]
    await observer.install()
    return observer


@pytest.mark.asyncio
async def test_an_observer_watching_the_live_body_is_left_alone() -> None:
    frame = _ScriptedFrame(False)
    observer = await _installed(frame)

    assert await observer.ensure_active() is False
    assert frame.installs == 1


@pytest.mark.asyncio
async def test_a_replaced_body_is_re_anchored_by_the_observer_in_the_page() -> None:
    frame = _ScriptedFrame(True)
    observer = await _installed(frame)

    assert await observer.ensure_active() is True
    assert frame.installs == 1


@pytest.mark.asyncio
async def test_a_new_document_without_an_observer_gets_one() -> None:
    frame = _ScriptedFrame(None)  # a click, form submit or redirect loaded another page: the old observer is gone
    observer = await _installed(frame)

    assert await observer.ensure_active() is True
    assert frame.installs == 2
    assert observer.is_installed


@pytest.mark.asyncio
async def test_a_new_document_that_cannot_take_an_observer_is_cross_origin() -> None:
    frame = _ScriptedFrame(None)
    observer = await _installed(frame)
    frame._install_fails = True

    assert await observer.ensure_active() is False
    assert observer.is_cross_origin
    assert not observer.is_installed


@pytest.mark.asyncio
async def test_a_frame_that_cannot_be_probed_is_cross_origin() -> None:
    frame = _ScriptedFrame(RuntimeError("blocked a frame with origin"))
    observer = await _installed(frame)

    assert await observer.ensure_active() is False
    assert observer.is_cross_origin
    assert not observer.is_installed
