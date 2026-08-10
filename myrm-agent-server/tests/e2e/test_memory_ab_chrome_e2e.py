"""Chrome E2E for the Memory A/B evaluation flow in the Eval Lab.

Covers:
  T1 (READ) - Every WBBench card shows a Memory A/B button; clicking it opens
              the confirmation dialog; Cancel closes it without starting a run.
  T2 (NAMESPACE_WRITE) - Pre-seeded reports render the dual-arm matrix (No Memory /
              With Memory rows + Memory Calls column), the Run History table shows
              per-arm pass rate with memory_tool_calls, and clicking a historical
              View button loads that run's report.
  T3 (NAMESPACE_WRITE) - Real user flow: confirming Start on the Office card starts
              a live Memory A/B run (SSE running state + header Stop button), and
              Stop aborts it so the shared stack is never left evaluating.

Prerequisites:
  ./myrm ready --chrome
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.wb_bench_e2e_helpers import (
    EVAL_LAB_PATH,
    SOURCES_READY_JS,
    all_cards_memory_ab_ready_js,
    click_subset_memory_ab_js,
    restore_eval_lab_route,
)

_SERVER_ROOT = Path(__file__).resolve().parents[2]

# The confirmation dialog opened by the Memory A/B button on a card.
_CONFIRM_DIALOG_VISIBLE_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const titleOk = /Start Memory A\\/B evaluation|开始记忆 A\\/B 评测/i.test(body);
  const startBtn = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /Start Evaluation|开始评测/.test(t);
  });
  const cancelBtn = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /^Cancel$|^取消$/.test(t);
  });
  return {
    ready: titleOk && !!startBtn && !!cancelBtn,
    titleOk,
    hasStart: !!startBtn,
    hasCancel: !!cancelBtn,
    bodyLength: body.length,
  };
})()"""

_CLICK_CONFIRM_CANCEL_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /^Cancel$|^取消$/.test(t);
  });
  if (!target) return { ok: false, err: 'cancel-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

_CLICK_CONFIRM_START_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /Start Evaluation|开始评测/.test(t);
  });
  if (!target) return { ok: false, err: 'start-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

_DIALOG_CLOSED_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  return { ready: !/Start Memory A\\/B evaluation|开始记忆 A\\/B 评测/i.test(body) };
})()"""

# Memory A/B report tab: dual-arm matrix + Run History table render from the
# seeded reports. The probe activates the memory-ab tab and asserts the No
# Memory / With Memory rows, the Memory Calls column, and the per-arm pass-rate
# cells with their memory_tool_calls counts (e.g. "50% (0)" / "100% (5)").
# Synchronous probe: wait_for_state re-polls it, so the first poll activates
# the tab and later polls observe the rendered report.
_MEMORY_AB_REPORT_RENDER_JS = """(() => {
  const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((b) =>
    /Memory A\\/B|记忆 A\\/B/i.test(b.textContent || ''),
  );
  if (!tab) return { ready: false, hasTab: false, reason: 'tab-missing' };
  if (tab.getAttribute('data-state') !== 'active') {
    const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
    tab.dispatchEvent(new PointerEvent('pointerdown', opts));
    tab.dispatchEvent(new MouseEvent('mousedown', opts));
    tab.dispatchEvent(new PointerEvent('pointerup', opts));
    tab.dispatchEvent(new MouseEvent('mouseup', opts));
    tab.dispatchEvent(new MouseEvent('click', opts));
  }
  const body = document.body?.innerText || document.body?.textContent || '';
  const hasNoMemory = /No Memory|无记忆/.test(body);
  const hasWithMemory = /With Memory|开启记忆/.test(body);
  const hasMemoryCalls = /Memory Calls|记忆调用次数/.test(body);
  const hasRunHistory = /Run History|运行历史/.test(body);
  const hasOffCell = /50%\\s*\\(0\\)/.test(body);
  const hasOnCell = /100%\\s*\\(5\\)/.test(body);
  return {
    ready: hasNoMemory && hasWithMemory && hasMemoryCalls && hasRunHistory && hasOffCell && hasOnCell,
    hasTab: true,
    hasNoMemory,
    hasWithMemory,
    hasMemoryCalls,
    hasRunHistory,
    hasOffCell,
    hasOnCell,
    bodyLength: body.length,
  };
})()"""

_CLICK_HISTORY_VIEW_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /^View$|^查看$/.test(t);
  });
  if (!target) return { ok: false, err: 'history-view-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

# After clicking View on the older history row the seeded older report loads:
# its unique case message appears in the matrix and the row becomes Current
# (selected, disabled).
_SELECTED_HISTORY_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const currentBtn = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /^Current$|^当前$/.test(t);
  });
  const agedLoaded = body.includes('Memory A/B case aged');
  return {
    ready: agedLoaded && !!currentBtn && currentBtn.disabled === true,
    agedLoaded,
    hasCurrent: !!currentBtn,
    currentDisabled: currentBtn ? currentBtn.disabled : null,
    bodyLength: body.length,
  };
})()"""

# A live Memory A/B run surfaces through the header Stop button, the memory-ab
# tab becoming active, and the running/downloading progress text in that tab.
# The frontend switches the active tab synchronously on a "started" response, so
# checking the active tab makes the probe robust while the run is still in its
# download stage (which shows "Downloading" instead of the running text).
_MEMORY_AB_RUNNING_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const stopBtn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Stop|停止/.test((b.textContent || '').trim()),
  );
  const runningText = /Memory A\\/B evaluation in progress|记忆 A\\/B 评测进行中/i.test(body);
  const activeTab = document.querySelector('[role="tab"][data-state="active"]');
  const tabActive =
    !!activeTab && /Memory A\\/B|记忆 A\\/B/i.test(activeTab.textContent || '');
  return {
    ready: !!stopBtn && (runningText || tabActive),
    hasStop: !!stopBtn,
    runningText,
    tabActive,
    bodyLength: body.length,
  };
})()"""

_CLICK_STOP_JS = """(() => {
  const target = Array.from(document.querySelectorAll('button')).find((b) => {
    const t = (b.textContent || '').trim();
    return /Stop|停止/.test(t);
  });
  if (!target) return { ok: false, err: 'stop-button-missing' };
  const opts = { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, detail: 1 };
  target.dispatchEvent(new PointerEvent('pointerdown', opts));
  target.dispatchEvent(new MouseEvent('mousedown', opts));
  target.dispatchEvent(new PointerEvent('pointerup', opts));
  target.dispatchEvent(new MouseEvent('mouseup', opts));
  target.dispatchEvent(new MouseEvent('click', opts));
  return { ok: true, clicked: true };
})()"""

_MEMORY_AB_CLEARED_JS = """(() => {
  const body = document.body?.innerText || document.body?.textContent || '';
  const stopBtn = Array.from(document.querySelectorAll('button')).find((b) =>
    /Stop|停止/.test((b.textContent || '').trim()),
  );
  const runningText = /Memory A\\/B evaluation in progress|记忆 A\\/B 评测进行中/i.test(body);
  return {
    ready: !stopBtn && !runningText,
    hasStop: !!stopBtn,
    runningText,
    bodyLength: body.length,
  };
})()"""


def _make_matrix_report(
    *,
    timestamp: int,
    case_suffix: str,
    off_calls: int,
    on_calls: int,
) -> dict[str, object]:
    """A minimal but structurally complete dual-arm MatrixReportData payload."""
    return {
        "profile_ids": ["memory_off", "memory_on"],
        "total_cases": 2,
        "stable_count": 1,
        "regression_count": 1,
        "stable_rate": 0.5,
        "per_profile": {
            "memory_off": {
                "pass_count": 1,
                "fail_count": 0,
                "error_count": 1,
                "pass_rate": 0.5,
                "total_tokens": 1000,
                "total_cost": 0.01,
                "total_ms": 20000,
                "memory_tool_calls": off_calls,
            },
            "memory_on": {
                "pass_count": 2,
                "fail_count": 0,
                "error_count": 0,
                "pass_rate": 1.0,
                "total_tokens": 2000,
                "total_cost": 0.02,
                "total_ms": 25000,
                "memory_tool_calls": on_calls,
            },
        },
        "matrix": [
            {
                "case_index": 0,
                "message": f"Memory A/B case {case_suffix}",
                "profiles": {
                    "memory_off": {
                        "passed": True,
                        "total_ms": 10000,
                        "token_usage": {"total": 500},
                        "cost": 0.005,
                        "error": None,
                    },
                    "memory_on": {
                        "passed": True,
                        "total_ms": 12000,
                        "token_usage": {"total": 600},
                        "cost": 0.006,
                        "error": None,
                    },
                },
            },
            {
                "case_index": 1,
                "message": "Regression case",
                "profiles": {
                    "memory_off": {
                        "passed": False,
                        "total_ms": 10000,
                        "token_usage": {"total": 500},
                        "cost": 0.005,
                        "error": "boom",
                    },
                    "memory_on": {
                        "passed": True,
                        "total_ms": 13000,
                        "token_usage": {"total": 600},
                        "cost": 0.006,
                        "error": None,
                    },
                },
            },
        ],
        "total_ms": 45000,
        "timestamp": timestamp,
        "dataset_id": "wb-bench-office",
        "profile_id": None,
        "benchmark_mode": True,
    }


@contextlib.contextmanager
def _seeded_memory_ab_reports() -> object:
    """Seed two reports (latest + older) into the shared server data dir.

    The memory-ab reports live under the server working directory
    (``.myrm/memory_ab_reports``); the server CWD is the server repo root, which
    this test resolves the same way ``wb_bench_e2e_helpers`` does.
    """
    reports_dir = _SERVER_ROOT / ".myrm/memory_ab_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest_path = reports_dir / "latest.json"
    had_latest = latest_path.exists()
    latest_backup = latest_path.read_bytes() if had_latest else b""

    now = int(time.time())
    older_ts = now - 200
    older_report = _make_matrix_report(
        timestamp=older_ts,
        case_suffix="aged",
        off_calls=0,
        on_calls=5,
    )
    latest_report = _make_matrix_report(
        timestamp=now,
        case_suffix="fresh",
        off_calls=1,
        on_calls=7,
    )

    created: list[Path] = []
    try:
        older_path = reports_dir / f"memory_ab_report_{older_ts}.json"
        older_path.write_text(
            json.dumps(older_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(older_path)

        # Mirrors run_memory_ab_background: the latest run exists both as a
        # timestamped file (scanned by the history endpoint) and as latest.json.
        latest_timestamped = reports_dir / f"memory_ab_report_{now}.json"
        latest_timestamped.write_text(
            json.dumps(latest_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(latest_timestamped)

        latest_path.write_text(
            json.dumps(latest_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        created.append(latest_path)
        yield None
    finally:
        for path in created:
            path.unlink(missing_ok=True)
        if had_latest:
            latest_path.write_bytes(latest_backup)
        else:
            latest_path.unlink(missing_ok=True)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_memory_ab_card_entry_and_confirm_dialog_chrome_e2e() -> None:
    """WBBench cards expose Memory A/B; the confirm dialog opens and cancels."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
        client,
        page,
    ):
        restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
        dismiss_blocking_modals(client, page)

        sources_ready = wait_for_state(
            client, page, SOURCES_READY_JS, timeout_sec=120.0
        )
        assert sources_ready.get("ready") is True, sources_ready

        buttons = wait_for_state(
            client, page, all_cards_memory_ab_ready_js(), timeout_sec=30.0
        )
        assert buttons.get("ready") is True, buttons

        clicked = client.evaluate(page, click_subset_memory_ab_js("WBBench Office"))
        assert clicked.get("ok") is True, clicked

        dialog = wait_for_state(
            client, page, _CONFIRM_DIALOG_VISIBLE_JS, timeout_sec=15.0
        )
        assert dialog.get("ready") is True, dialog

        cancelled = client.evaluate(page, _CLICK_CONFIRM_CANCEL_JS)
        assert cancelled.get("ok") is True, cancelled

        closed = wait_for_state(client, page, _DIALOG_CLOSED_JS, timeout_sec=15.0)
        assert closed.get("ready") is True, closed


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_ab_report_and_history_render_chrome_e2e() -> None:
    """Seeded Memory A/B reports render the matrix + history; View loads one."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with _seeded_memory_ab_reports():
        with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
            client,
            page,
        ):
            restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
            dismiss_blocking_modals(client, page)

            render = wait_for_state(
                client, page, _MEMORY_AB_REPORT_RENDER_JS, timeout_sec=60.0
            )
            assert render.get("ready") is True, render

            clicked = client.evaluate(page, _CLICK_HISTORY_VIEW_JS)
            assert clicked.get("ok") is True, clicked

            selected = wait_for_state(
                client, page, _SELECTED_HISTORY_JS, timeout_sec=30.0
            )
            assert selected.get("ready") is True, selected


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_ab_real_run_starts_and_can_abort_chrome_e2e() -> None:
    """Confirming Start on a card launches a real Memory A/B run and Stop aborts it."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())
    warm_ui_route(EVAL_LAB_PATH)

    with open_mcp_page(f"{ui_url}{EVAL_LAB_PATH}", timeout_ms=120_000) as (
        client,
        page,
    ):
        restore_eval_lab_route(client, page, f"{ui_url}{EVAL_LAB_PATH}")
        dismiss_blocking_modals(client, page)

        sources_ready = wait_for_state(
            client, page, SOURCES_READY_JS, timeout_sec=120.0
        )
        assert sources_ready.get("ready") is True, sources_ready

        clicked = client.evaluate(page, click_subset_memory_ab_js("WBBench Office"))
        assert clicked.get("ok") is True, clicked

        dialog = wait_for_state(
            client, page, _CONFIRM_DIALOG_VISIBLE_JS, timeout_sec=15.0
        )
        assert dialog.get("ready") is True, dialog

        started = client.evaluate(page, _CLICK_CONFIRM_START_JS)
        assert started.get("ok") is True, started

        inflight = wait_for_state(
            client, page, _MEMORY_AB_RUNNING_JS, timeout_sec=120.0
        )
        assert inflight.get("ready") is True, inflight

        stopped = client.evaluate(page, _CLICK_STOP_JS)
        assert stopped.get("ok") is True, stopped

        cleared = wait_for_state(client, page, _MEMORY_AB_CLEARED_JS, timeout_sec=90.0)
        assert cleared.get("ready") is True, cleared
