"""Chrome E2E: featured expert chips on the empty chat render their own Lucide icon, loaded on demand.

Real user flow on ``/``: a new chat shows featured expert chips. Each template names its icon as
``lucide:<name>`` and the chip resolves it through the per-icon lazy resolver (one chunk per icon, not
the whole icon set). The real templates API supplies the icon names; every featured chip must end up
rendering its own ``<svg class="lucide-<name>">`` rather than staying on the Bot/Users placeholder.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_LUCIDE_PREFIX = "lucide:"
_PLACEHOLDER_ICONS = {"bot", "users"}  # shown while an icon chunk loads, and for unknown names
_FEATURED_LIMIT = 5


def _featured_rank(template: dict[str, object]) -> tuple[int, int, int]:
    """Mirror FeaturedExpertChips ordering: teams, then Pareto presets, then richer use cases first."""
    use_cases = template.get("use_cases")
    return (
        0 if template.get("agent_type") == "team" else 1,
        0 if template.get("is_pareto_preset") else 1,
        -(len(use_cases) if isinstance(use_cases, list) else 0),
    )


def _featured_icons(api_url: str) -> list[str]:
    """Lucide icon name per featured chip, in display order ('' when the template declares none)."""
    body = http_json("GET", f"{api_url}/api/v1/agents/templates")
    assert isinstance(body, dict), body
    templates = body["data"]
    assert isinstance(templates, list), body
    featured = sorted(templates, key=_featured_rank)[:_FEATURED_LIMIT]
    return [
        avatar.removeprefix(_LUCIDE_PREFIX)
        if isinstance(avatar := tpl.get("avatar_url"), str) and avatar.startswith(_LUCIDE_PREFIX)
        else ""
        for tpl in featured
    ]


def _chips_js(icons: list[str]) -> str:
    # Per-icon lazy chunks render through lucide's generic <Icon>, which only carries the ``lucide`` class
    # (no ``lucide-<name>``); the Bot/Users placeholders are named classes. A resolved chip therefore has an
    # unnamed svg whose geometry is unique per distinct icon; chips are matched by position because the page
    # may be localized differently from the API call.
    return f"""(() => {{
  const expected = {json.dumps(icons)};
  const placeholders = {json.dumps(sorted(_PLACEHOLDER_ICONS))}.map((name) => 'lucide-' + name);
  const root = document.querySelector('[data-testid="empty-chat-featured-chips"]');
  const chips = root ? Array.from(root.querySelectorAll(':scope > div > button')) : [];
  const avatars = chips.map((chip) => chip.querySelector('span svg'));
  const resolved = avatars.map((svg) => !!svg && svg.classList.contains('lucide')
    && !placeholders.some((cls) => svg.classList.contains(cls)) && svg.children.length > 0);
  const geometry = avatars.map((svg) => (svg ? svg.innerHTML : ''));
  const wantedIdx = expected.map((icon, i) => (icon ? i : -1)).filter((i) => i >= 0);
  const unresolved = wantedIdx.filter((i) => !resolved[i]);
  const distinct = new Set(wantedIdx.map((i) => geometry[i])).size;
  const distinctExpected = new Set(wantedIdx.map((i) => expected[i])).size;
  return {{
    ready: chips.length === expected.length && unresolved.length === 0 && distinct === distinctExpected,
    expected, unresolved, distinct, distinctExpected,
    avatarClasses: avatars.map((svg) => (svg ? svg.getAttribute('class') : null)),
  }};
}})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_featured_expert_chips_render_lazy_lucide_icons() -> None:
    """The empty chat renders a template's Lucide icon (not just the Bot placeholder) in a real browser."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    icons = _featured_icons(api_url)
    # Placeholder-only icons cannot prove the lazy load: a featured chip must name a real, distinct icon.
    assert set(icons) - _PLACEHOLDER_ICONS - {""}, f"no featured template declares a lucide icon: {icons}"

    warm_ui_route("/")
    with open_mcp_page(f"{get_e2e_ui_url().rstrip('/')}/", timeout_ms=120_000) as (client, page):
        state = wait_for_state(client, page, _chips_js(icons), timeout_sec=120.0)
        assert state.get("ready") is True, state
