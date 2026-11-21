"""Unit tests for the expression the agent's JavaScript reaches the browser as (``domain_filter.agent_world``).

What the browser then does with it, in a real Chromium, is proven in ``test_agent_world_policy_integration.py``; these
tests pin when an expression is armed, what the arm carries, and that the agent's own text reaches the inner
``eval`` exactly as written.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist, agent_world, scripts
from myrm_agent_harness.toolkits.browser.domain_filter.agent_world import agent_world_expression
from myrm_agent_harness.toolkits.browser.domain_filter.context_lists import DomainListPolicy, bind_domain_lists


class _Context:
    """Hashable, weak-referenceable stand-in for a ``BrowserContext``: the lists are keyed by the object."""


def _context(*, allow: tuple[str, ...] = (), block: tuple[str, ...] = ()) -> _Context:
    context = _Context()
    blocklist = DomainAllowlist.from_strings(block) if block else None
    bind_domain_lists(context, DomainListPolicy(DomainAllowlist.from_strings(allow), blocklist))  # type: ignore[arg-type]
    return context


def _armed(context: _Context, expression: str) -> str:
    return agent_world_expression(context, expression)  # type: ignore[arg-type]


def _arm_of(armed: str) -> str:
    """Everything before the inner ``eval`` of the agent's expression."""
    return armed.partition(agent_world._RUN_HEAD)[0]


def _inner_expression(armed: str) -> str:
    """The text the arm hands to the inner ``eval``, read back from its JSON literal."""
    run = armed.removeprefix(_arm_of(armed))
    assert run.startswith(agent_world._RUN_HEAD), run[:40]
    assert run.endswith(agent_world._RUN_TAIL), run[-40:]
    text: str = json.loads(run.removeprefix(agent_world._RUN_HEAD).removesuffix(agent_world._RUN_TAIL))
    return text


@pytest.fixture(autouse=True)
def _fresh_arm_cache() -> Iterator[None]:
    agent_world._arm.cache_clear()
    yield
    agent_world._arm.cache_clear()


class TestWhenTheExpressionIsLeftAlone:
    def test_a_context_without_lists_runs_the_expression_as_written(self) -> None:
        assert _armed(_Context(), "  document.title ") == "  document.title "

    def test_a_blocklist_alone_needs_no_arm(self) -> None:
        """Only an allowlist becomes a Content-Security-Policy and a hardened window; a blocklist is Layer 1's."""
        assert _armed(_context(block=("bad.example",)), "document.title") == "document.title"


class TestTheArm:
    def test_it_carries_the_allowlists_policy_the_hardening_and_the_refusal(self) -> None:
        armed = _armed(_context(allow=("example.com",)), "document.title")

        assert "connect-src 'self' example.com" in armed
        assert "RTCPeerConnection blocked by domain policy" in armed
        assert "JS evaluation refused" in armed

    def test_it_sets_a_window_up_once_and_does_not_let_the_agent_unset_its_check(self) -> None:
        """The policy script wraps the constructors, so a window is set up once; a plain global could be deleted."""
        arm = _arm_of(_armed(_context(allow=("example.com",)), "1"))

        assert arm.startswith("if (!globalThis.__myrmDomainPolicy) {")
        assert "Object.defineProperty(globalThis, '__myrmDomainPolicy'" in arm
        assert arm.index("RTCPeerConnection blocked") < arm.index("if (!globalThis.__myrmDomainPolicy())")

    def test_it_is_built_once_per_allowlist_whatever_the_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        builds: list[DomainAllowlist] = []
        real = scripts.build_csp_meta_script

        def counting(allowlist: DomainAllowlist) -> str:
            builds.append(allowlist)
            return real(allowlist)

        monkeypatch.setattr(agent_world, "build_csp_meta_script", counting)
        first, same, other = (
            _context(allow=("a.example",)),
            _context(allow=("a.example",)),
            _context(allow=("b.example",)),
        )

        arms = {_arm_of(_armed(first, "1")), _arm_of(_armed(first, "2")), _arm_of(_armed(same, "3"))}
        assert len(arms) == 1
        assert len(builds) == 1

        assert _arm_of(_armed(other, "1")) not in arms
        assert len(builds) == 2


class TestTheAgentsExpression:
    @pytest.mark.parametrize(
        "expression",
        [
            "document.title",
            "1 + 1 // a trailing comment",
            "'use strict'; (function () { return this; })()",
            'const a = {k: "v\\n"}; a.k',
            "[...'a\u2028b\u2029c'].length",
            "'</script><!-- \U0001f600'",
            "(async () => { await 0; return 1; })()",
            "() => 41 + 1",
            "async () => 'arrow'",
            "function named() { return 1; }",
            "async  function () { return 1; }",
            "\n\t document.title \n",
            "\ufefffunction () { return 'bom'; }",
            "1)); throw new Error('escaped'); ((1",
        ],
    )
    def test_it_reaches_the_inner_eval_as_one_literal_that_cannot_end_early(self, expression: str) -> None:
        """Nothing is trimmed, wrapped or escaped on this side: the text the agent wrote is what the literal holds."""
        armed = _armed(_context(allow=("example.com",)), expression)

        assert _inner_expression(armed) == expression
        assert armed.removeprefix(_arm_of(armed)).isascii()

    def test_the_page_decides_what_is_whitespace_and_what_reads_as_a_function(self) -> None:
        """The driver trims the text and parenthesizes a function expression; ``eval`` would take it for a declaration.

        Both steps run in the page's own JavaScript engine, which is the engine the driver's rule runs in, so the two
        never disagree about which characters are whitespace (a unit test cannot run them; the integration test
        compares both outcomes for texts the two readings of whitespace part on).
        """
        assert "text.trim()" in agent_world._RUN_HEAD
        assert r"/^(async)?\s*function(\s|\()/" in agent_world._RUN_HEAD
        assert "'(' + text + ')'" in agent_world._RUN_HEAD
