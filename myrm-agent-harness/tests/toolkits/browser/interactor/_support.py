"""Builders shared by the CAREFUL pre-scroll tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from myrm_agent_harness.toolkits.browser.pool.config import HumanizeConfig, HumanizeMode
from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo


def careful_interactor(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> Interactor:
    return Interactor(mock_page, refs_map, humanize=HumanizeConfig.from_mode(HumanizeMode.CAREFUL))


def target_probe(
    *,
    visible: bool = True,
    is_top: bool = True,
    x: float = 100,
    y: float = 0,
    width: float = 200,
    height: float = 100,
    container: dict[str, object] | None = None,
) -> dict[str, object]:
    """Rendered-state dict returned by _TARGET_PROBE_JS."""
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "visible": visible,
        "is_top": is_top,
        "container": container,
    }


def doc_container(delta: int) -> dict[str, object]:
    """The main document as the scroll container."""
    return {
        "left": 0,
        "top": 0,
        "width": 1280,
        "height": 720,
        "is_doc": True,
        "delta": delta,
    }
