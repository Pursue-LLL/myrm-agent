"""Interactor ref bookkeeping: initialization, metrics, ref resolution and self-healing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.exceptions import (
    RefNotFoundError,
)
from myrm_agent_harness.toolkits.browser.session.interactor import Interactor
from myrm_agent_harness.toolkits.browser.snapshot import RefInfo

# =============================================================================
# Initialization
# =============================================================================


def test_interactor_init(mock_page: MagicMock, refs_map: dict[str, RefInfo]) -> None:
    """Test Interactor initialization."""
    interactor = Interactor(mock_page, refs_map)

    assert interactor._page is mock_page
    assert interactor._refs == refs_map


def test_interactor_update_refs(interactor: Interactor, ref_info: RefInfo) -> None:
    """Test update_refs method."""
    new_refs = {"e1": ref_info}

    interactor.update_refs(new_refs)

    assert interactor._refs == new_refs


# =============================================================================
# Metrics and context
# =============================================================================


def test_metrics_empty():
    from myrm_agent_harness.toolkits.browser.session.ref_metrics import (
        RefNotFoundMetrics,
    )

    metrics = RefNotFoundMetrics()
    assert metrics.failure_rate == 0.0
    assert metrics.recent_failure_rate == 0.0
    assert metrics.top_failed_refs == []
    assert metrics.top_failed_actions == []
    d = metrics.to_dict()
    assert d["total_failures"] == 0


def test_metrics_caching():
    from myrm_agent_harness.toolkits.browser.session.ref_metrics import (
        RefNotFoundMetrics,
    )

    metrics = RefNotFoundMetrics()
    metrics.record_interaction(failed=True, ref="e1", action="click")
    assert metrics.top_failed_refs == [("e1", 1)]
    assert metrics.top_failed_actions == [("click", 1)]
    # Test cache
    assert metrics.top_failed_refs == [("e1", 1)]
    assert metrics.top_failed_actions == [("click", 1)]


def test_update_refs():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {})
    interactor.update_refs({"e1": RefInfo(role="link", name="L", nth=0)}, last_snapshot_url="http://new")
    assert "e1" in interactor._refs
    assert interactor._last_snapshot_url == "http://new"


def test_get_context_refs_limit():
    page = AsyncMock(spec=Page)
    refs = {f"e{i}": RefInfo(role="link", name=f"L{i}", nth=0) for i in range(20)}
    interactor = Interactor(page, refs)
    res = interactor._get_context_refs(max_total=5)
    assert len(res) == 5


def test_metrics_property():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {})
    from myrm_agent_harness.toolkits.browser.session.ref_metrics import (
        RefNotFoundMetrics,
    )

    assert isinstance(interactor.metrics, RefNotFoundMetrics)


def test_log_metrics_if_needed():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {})
    interactor._metrics.total_interactions = 100
    interactor._metrics.total_failures = 1
    with patch("myrm_agent_harness.toolkits.browser.session.ref_metrics.logger.info") as mock_info:
        interactor._log_metrics_if_needed()
        mock_info.assert_called_once()


def test_resolve_frame():
    page = AsyncMock(spec=Page)
    frame = AsyncMock()
    page.frames = [page, frame]
    interactor = Interactor(page, {})
    assert interactor._resolve_frame("f1_e0") == frame
    assert interactor._resolve_frame("f99_e0") == page
    assert interactor._resolve_frame("fX_e0") == page


# =============================================================================
# Ref resolution
# =============================================================================


@pytest.mark.asyncio
async def test_interact_invalid_action(interactor: Interactor) -> None:
    """Test interact with invalid action raises ValueError."""
    with pytest.raises(ValueError, match="Invalid action"):
        await interactor.interact("invalid_action", "e0")


@pytest.mark.asyncio
async def test_interact_self_healing():
    page = AsyncMock(spec=Page)
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_loc.wait_for.side_effect = Exception("timeout")
        mock_resolve.return_value = mock_loc

        with patch(
            "myrm_agent_harness.toolkits.browser.snapshot.self_healer.SelfHealer.heal",
            new_callable=AsyncMock,
        ) as mock_heal:
            healed_loc = AsyncMock()
            mock_heal.return_value = (healed_loc, "NewName", 0.5)

            with patch("myrm_agent_harness.runtime.events.bus.get_event_bus") as mock_bus:
                mock_bus.return_value.publish = MagicMock()
                res = await interactor.interact("click", "e0")
                assert "Auto-Healed" in res
                assert "NewName" in res
                healed_loc.click.assert_called_once()
    page = AsyncMock(spec=Page)
    page.evaluate.side_effect = Exception("error")  # the post-action wait cannot probe the page
    interactor = Interactor(page, {"e0": RefInfo(role="button", name="B", nth=0)})

    with patch("myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator") as mock_resolve:
        mock_loc = AsyncMock()
        mock_resolve.return_value = mock_loc

        res = await interactor.interact("click", "e0")
        assert "Clicked" in res


@pytest.mark.asyncio
async def test_interact_ref_not_found(interactor: Interactor) -> None:
    """Test interact with non-existent ref raises RefNotFoundError."""
    with pytest.raises(RefNotFoundError, match="Ref not found: e999"):
        await interactor.interact("click", "e999")


@pytest.mark.asyncio
async def test_interactor_multiple_refs(mock_page: MagicMock) -> None:
    """Test Interactor with multiple refs."""
    refs = {
        "e0": RefInfo("button", "Submit", None, {"x": 100, "y": 50}, "center-center"),
        "e1": RefInfo("textbox", "Email", None, {"x": 100, "y": 100}, "center-center"),
        "e2": RefInfo("checkbox", "Terms", None, {"x": 100, "y": 150}, "center-center"),
    }

    interactor = Interactor(mock_page, refs)

    mock_locator = AsyncMock()
    mock_locator.get_attribute.return_value = "text"

    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        await interactor.interact("click", "e0")
        await interactor.interact("fill", "e1", "test@example.com")
        await interactor.interact("check", "e2")

        assert mock_locator.click.call_count == 1
        assert mock_locator.fill.call_count == 1
        assert mock_locator.check.call_count == 1


@pytest.mark.asyncio
async def test_interactor_update_refs_and_use(mock_page: MagicMock, ref_info: RefInfo) -> None:
    """Test updating refs and using new refs."""
    interactor = Interactor(mock_page, {})

    with pytest.raises(RefNotFoundError, match="Ref not found"):
        await interactor.interact("click", "e0")

    interactor.update_refs({"e0": ref_info})

    mock_locator = AsyncMock()
    with patch(
        "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
        return_value=mock_locator,
    ):
        result = await interactor.interact("click", "e0")
        assert "Clicked e0" in result


@pytest.mark.asyncio
async def test_interactor_unknown_action_coverage(mock_page: MagicMock, ref_info: RefInfo) -> None:
    """测试未知action的返回（覆盖line 178，理论死代码）"""
    from myrm_agent_harness.toolkits.browser.session import (
        interactor as interactor_module,
    )

    # 临时添加一个不在elif链中的action来触发line 178
    original_actions = interactor_module._VALID_ACTIONS
    interactor_module._VALID_ACTIONS = frozenset(original_actions | {"unknown_action"})

    try:
        test_interactor = Interactor(mock_page, {"e0": ref_info})

        mock_locator = AsyncMock()
        with patch(
            "myrm_agent_harness.toolkits.browser.session.interactor.resolve_locator",
            return_value=mock_locator,
        ):
            result = await test_interactor.interact("unknown_action", "e0", "")
            assert result == "Unknown action: unknown_action"
    finally:
        interactor_module._VALID_ACTIONS = original_actions
