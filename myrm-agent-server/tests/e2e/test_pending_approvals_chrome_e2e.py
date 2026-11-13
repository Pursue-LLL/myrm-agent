"""Real Chrome E2E: kanban IN_REVIEW tasks count as pending approvals until reviewed.

The IN_REVIEW state is only reachable after a real agent completes a
require_approval run, which an E2E probe cannot dispatch. The server exposes a
local-only fixture endpoint (`POST /chats/test/seed-kanban-in-review-fixture`)
that drives the real KanbanService/store — the backend stays the single writer,
so no second sqlite3 writer can corrupt its WAL. The test then verifies the
badges `pendingApprovals` count ticks up, that the in-review deep link (the one
push notifications and task toasts open) lands on the pending task, and that
the count falls back after the approve (IN_REVIEW -> COMPLETED) and reject
(IN_REVIEW -> READY) transitions, both performed like a real user inside the
kanban task drawer.

Incremental assertions (N -> N+1 -> N) immunize against concurrent activity
from other developers sharing the server.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

# Raw English display names of built-in agents (from builtin-agent-i18n-data).
# A zh kanban drawer must never render these verbatim; localization replaces
# them via getBuiltinAgentName.
_KNOWN_BUILTIN_ENGLISH_NAMES: tuple[str, ...] = (
    "General Assistant",
    "Deep Researcher",
    "Data Analyst",
    "Scheduled Agent",
    "Code Assistant",
    "Wiki Agent",
    "Sub-agent",
)


def _api_pending_approvals(api_url: str) -> int:
    """Server-side pendingApprovals (goal approvals + kanban IN_REVIEW)."""
    body = http_json("GET", f"{api_url}/api/v1/statistics/badges")
    return int(body["data"]["pendingApprovals"])


def _wait_pending_approvals(api_url: str, expected: int, *, timeout_sec: float = 15.0) -> int:
    """Poll the badges API until it settles on ``expected``."""
    deadline = time.monotonic() + timeout_sec
    last = -1
    while time.monotonic() < deadline:
        last = _api_pending_approvals(api_url)
        if last == expected:
            return last
        time.sleep(1.0)
    return last


def _seed_in_review(api_url: str) -> dict[str, str]:
    """Create an IN_REVIEW task through the server fixture (single writer)."""
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-kanban-in-review-fixture")
    assert isinstance(seeded, dict)
    board_id = str(seeded.get("board_id") or "")
    task_id = str(seeded.get("task_id") or "")
    task_title = str(seeded.get("task_title") or "")
    board_name = str(seeded.get("board_name") or "")
    agent_id = str(seeded.get("agent_id") or "")
    assert board_id and task_id and task_title and board_name
    return {
        "board_id": board_id,
        "task_id": task_id,
        "task_title": task_title,
        "board_name": board_name,
        "agent_id": agent_id,
    }


def _verify_in_review_deep_link(
    client: object,
    page: object,
    *,
    ui_url: str,
    board_id: str,
    board_name: str,
    task_id: str,
) -> None:
    """Open the in-review deep link and verify it lands on the pending task.

    `/settings/kanban?board_id=…&status=in_review` is the link push
    notifications and task toasts open. It must land on the board with the
    status filter chip rendered and the pending task card present.
    """
    target_url = f"{ui_url}/settings/kanban?board_id={board_id}&status=in_review"
    navigate_mcp_page(client, page, target_url, timeout_ms=90_000)
    landed = wait_for_state(
        client,
        page,
        f"""(() => {{
          const view = document.querySelector('[data-testid="kanban-board-view"]');
          const filter = document.querySelector(
            '[data-testid="kanban-status-filter"]',
          );
          const card = document.getElementById('kanban-task-' + {task_id!r});
          const text = view?.textContent || '';
          const inBoard = !!view && text.includes({board_name!r});
          return {{
            ready: !!view && !!filter && !!card && inBoard,
            view: !!view,
            filter: !!filter,
            card: !!card,
            inBoard,
            url: location.pathname + location.search,
            text: text.slice(0, 300),
          }};
        }})()""",
        timeout_sec=90.0,
        page_url=target_url,
    )
    assert landed.get("ready") is True, f"in-review deep link did not land on the pending task: {landed}"


def _open_task_drawer_and_click(
    client: object,
    page: object,
    *,
    ui_url: str,
    board_id: str,
    board_name: str,
    task_id: str,
    action: str,
    reject_reason: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Open the kanban board, click the task card, then approve/reject in the
    drawer — every step through the real UI like a user."""
    kanban_url = f"{ui_url}/settings/kanban?board_id={board_id}"
    navigate_mcp_page(client, page, kanban_url, timeout_ms=90_000)
    view_state = wait_for_state(
        client,
        page,
        f"""(() => {{
          const view = document.querySelector('[data-testid="kanban-board-view"]');
          const text = view?.textContent || '';
          return {{ ready: !!view && text.includes({board_name!r}), text }};
        }})()""",
        timeout_sec=120.0,
        page_url=kanban_url,
    )
    assert board_name in str(view_state.get("text") or "")

    card_ready = wait_for_state(
        client,
        page,
        f"""(() => {{
          const card = document.getElementById('kanban-task-' + {task_id!r});
          return {{ ready: !!card, hasCard: !!card }};
        }})()""",
        timeout_sec=90.0,
        page_url=kanban_url,
    )
    assert card_ready.get("hasCard") is True

    # Open the drawer like a real user would (double-click the card). Keep the
    # dispatch synchronous (no Promise in the evaluated script) so the CDP
    # Runtime.evaluate result stays trivially serializable.
    opened = client.evaluate(
        page,
        f"""(() => {{
          const card = document.getElementById('kanban-task-' + {task_id!r});
          if (!card) return {{ opened: false, reason: 'card-not-found' }};
          window.__e2eErrors = [];
          window.onerror = (msg, src, line, col, errObj) => {{
            window.__e2eErrors.push(
              `error: ${{msg}} @ ${{src}}:${{line}}`
              + (errObj && errObj.stack ? ` | ${{errObj.stack.split('\\n').slice(0, 3).join(' <- ')}}` : ''),
            );
            return false;
          }};
          window.addEventListener('unhandledrejection', (e) => {{
            const r = (e && e.reason) || {{}};
            window.__e2eErrors.push(
              `rejection: ${{r.stack || String(r)}}`,
            );
          }});
          card.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true }}));
          return {{ opened: true, url: location.href }};
        }})()""",
        timeout_sec=5.0,
    )
    assert opened.get("opened") is True, f"dblclick open failed: {opened}"

    # The drawer mounts asynchronously (task detail fetch), so wait until the
    # action control for the requested review state is actually rendered.
    action_testid = "kanban-task-approve" if action == "approve" else "kanban-task-reject"
    drawer_state = wait_for_state(
        client,
        page,
        f"""(() => {{
          const drawer =
            document.querySelector('[data-testid="kanban-task-drawer"]')
            || document.querySelector('[role="dialog"]');
          const btn = document.querySelector('[data-testid="{action_testid}"]');
          return {{
            ready: !!drawer && !!btn,
            drawer: !!drawer,
            actionBtn: !!btn,
            errors: (window.__e2eErrors || []).slice(-8),
            overlay: !!document.querySelector('nextjs-portal, nextjs-error-overlay'),
          }};
        }})()""",
        timeout_sec=90.0,
        page_url="/settings/kanban",
    )
    if not drawer_state.get("actionBtn"):
        diag = client.evaluate(
            page,
            """(() => {
              const errors = (window.__e2eErrors || []).slice(-10);
              const overlay = !!document.querySelector('nextjs-portal, nextjs-error-overlay');
              const bodySnippet = (document.body?.innerText || '').slice(0, 400);
              return { errors, overlay, bodySnippet };
            })()""",
            timeout_sec=10.0,
        )
        raise AssertionError(f"kanban drawer did not render approve/reject; state={drawer_state} diag={diag}")
    assert drawer_state.get("actionBtn") is True, drawer_state

    if agent_id:
        # The seeded task is bound to a built-in agent; the drawer's agent
        # select must render a localized name (not a raw English leak in zh).
        # Poll because the drawer's agents come from an async store fetch.
        agent_state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const select = document.querySelector(
                '[data-testid="kanban-task-agent-select"]',
              );
              const lang = (document.documentElement.lang || '').toLowerCase();
              const isZh = lang.startsWith('zh');
              const options = select
                ? Array.from(select.options).map((o) => o.textContent.trim())
                : [];
              const selectedText = select
                ? (select.selectedOptions[0]?.textContent || '').trim()
                : '';
              const knownEnglish = {list(_KNOWN_BUILTIN_ENGLISH_NAMES)!r};
              const leaksEnglish = isZh
                ? options.some((o) => knownEnglish.includes(o))
                : false;
              const ready = !!select && options.length > 0 && !!selectedText;
              return {{
                ready,
                hasSelect: !!select,
                options,
                selectedText,
                leaksEnglish,
                isZh,
                lang,
              }};
            }})()""",
            timeout_sec=45.0,
        )
        assert agent_state.get("ready") is True, agent_state
        assert agent_state.get("leaksEnglish") is False, (
            f"zh kanban drawer leaked raw English built-in agent name; state={agent_state}"
        )
        assert agent_state.get("selectedText"), (
            f"kanban drawer agent select should show a selected agent name; state={agent_state}"
        )

    if action == "approve":
        clicked = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector('[data-testid="kanban-task-approve"]');
              if (!btn) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True, "approve button not found in the drawer"
    elif action == "reject":
        assert reject_reason is not None
        clicked = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector('[data-testid="kanban-task-reject"]');
              if (!btn) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert clicked is True, "reject button not found in the drawer"
        reason_set = client.evaluate(
            page,
            f"""(() => {{
              const area = document.querySelector(
                '[data-testid="kanban-task-reject-reason"]',
              );
              if (!area) return false;
              const setter = Object.getOwnPropertyDescriptor(
                HTMLTextAreaElement.prototype, 'value',
              ).set;
              setter.call(area, {reject_reason!r});
              area.dispatchEvent(new Event('input', {{ bubbles: true }}));
              return true;
            }})()""",
            timeout_sec=5.0,
        )
        assert reason_set is True
        confirmed = client.evaluate(
            page,
            """(() => {
              const btn = document.querySelector(
                '[data-testid="kanban-task-reject-confirm"]',
              );
              if (!btn) return false;
              btn.click();
              return true;
            })()""",
            timeout_sec=5.0,
        )
        assert confirmed is True, "reject confirm button not found"
    else:
        raise AssertionError(f"unknown drawer action {action!r}")


# exclusive_backend reason: asserts exact global /api/v1/statistics/badges pendingApprovals delta (after == before + 1).
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
def test_kanban_in_review_counts_as_pending_approval_until_reviewed() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    warm_ui_route("/settings/kanban")
    kanban_url = f"{ui_url}/settings/kanban"

    with open_mcp_page(kanban_url) as (client, page):
        navigate_mcp_page(client, page, kanban_url, timeout_ms=90_000)
        api_before = _api_pending_approvals(api_url)

        # Lifecycle 1: IN_REVIEW -> approve -> COMPLETED releases the pending count.
        seeded_apr = _seed_in_review(api_url)
        api_after = _wait_pending_approvals(api_url, api_before + 1)
        assert api_after == api_before + 1, (
            f"badges API must count the seeded IN_REVIEW task: api_before={api_before} actual={api_after}"
        )

        # Number-to-action: the in-review deep link lands on the pending task.
        _verify_in_review_deep_link(
            client,
            page,
            ui_url=ui_url,
            board_id=seeded_apr["board_id"],
            board_name=seeded_apr["board_name"],
            task_id=seeded_apr["task_id"],
        )

        _open_task_drawer_and_click(
            client,
            page,
            ui_url=ui_url,
            board_id=seeded_apr["board_id"],
            board_name=seeded_apr["board_name"],
            task_id=seeded_apr["task_id"],
            action="approve",
            agent_id=seeded_apr["agent_id"],
        )
        api_released = _wait_pending_approvals(api_url, api_before)
        assert api_released == api_before, (
            f"badges API must fall back after approve: api_before={api_before} actual={api_released}"
        )

        # Lifecycle 2: IN_REVIEW -> reject -> READY also releases the pending count.
        seeded_rej = _seed_in_review(api_url)
        api_after_rej = _wait_pending_approvals(api_url, api_before + 1)
        assert api_after_rej == api_before + 1, (
            f"badges API must count the second seeded IN_REVIEW task: api_before={api_before} actual={api_after_rej}"
        )

        _open_task_drawer_and_click(
            client,
            page,
            ui_url=ui_url,
            board_id=seeded_rej["board_id"],
            board_name=seeded_rej["board_name"],
            task_id=seeded_rej["task_id"],
            action="reject",
            reject_reason="e2e reject",
            agent_id=seeded_rej["agent_id"],
        )
        api_released_rej = _wait_pending_approvals(api_url, api_before)
        assert api_released_rej == api_before, (
            f"badges API must fall back after reject: api_before={api_before} actual={api_released_rej}"
        )
