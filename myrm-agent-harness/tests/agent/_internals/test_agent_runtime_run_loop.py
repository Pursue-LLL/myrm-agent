"""Tests for how run_agent_loop is wired and for the helpers it calls.

The wiring tests read the module's syntax tree for what the loop calls, in which order and with which arguments; the
helper tests exercise the checkpoint-safe merged context and the effective round budget.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestRunAgentLoopCatalogWiring:
    """The catalog and history seams sit where the turn is assembled; behavior lives in their own test files."""

    @staticmethod
    def _awaited_calls() -> list[str]:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        return [ast.unparse(n.value) for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Await)]

    def test_new_message_turn_resolves_history_before_it_delivers_the_catalog(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        history_idx = source.index("await resolve_turn_history(")
        build_idx = source.index("build_messages(query, fed_history)", history_idx)
        inject_idx = source.index("inject_datetime_tags(messages, fed_history, query)", build_idx)
        catalog_idx = source.index("await deliver_bound_skills_catalog(messages, agent_state, history)", inject_idx)
        assert history_idx < build_idx < inject_idx < catalog_idx
        assert catalog_idx - inject_idx < 200

    def test_resume_syncs_the_skill_index_without_rewriting_the_checkpoint(self) -> None:
        awaits = self._awaited_calls()
        assert any("sync_bound_skills_for_resume(" in awaited for awaited in awaits)
        assert not any("update_state" in awaited for awaited in awaits)

    def test_resume_reports_itself_without_resolving_history(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        resume_idx = source.index("record_turn_context(resumed_turn_facts())")
        assert source.index("await sync_bound_skills_for_resume(") < resume_idx
        assert resume_idx < source.index("await resolve_turn_history(")

    def test_history_mode_declaration_is_consumed_before_the_context_reaches_middleware(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        calls = {ast.unparse(node) for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)}
        assert "merged_context.pop(HISTORY_MODE_CONTEXT_KEY, None)" in calls


class TestPopCheckpointIncompatibleMergedContext:
    """No callable remains in merged_context: the LangGraph checkpoint cannot serialize one."""

    def test_file_content_reader_stripped_from_merged_context(self) -> None:
        from myrm_agent_harness.agent._internals._agent_helpers import (
            pop_checkpoint_incompatible_merged_context,
        )

        async def reader(_file_id: str) -> bytes:
            return b""

        merged: dict[str, object] = {
            "workspace_root": "/tmp",
            "session_id": "sess-1",
            "file_content_reader": reader,
        }

        stripped = pop_checkpoint_incompatible_merged_context(merged)

        assert "file_content_reader" not in merged
        assert callable(stripped["file_content_reader"])
        assert merged == {"workspace_root": "/tmp", "session_id": "sess-1"}

    def test_all_checkpoint_callbacks_stripped(self) -> None:
        from myrm_agent_harness.agent._internals._agent_helpers import (
            pop_checkpoint_incompatible_merged_context,
        )

        goal_provider = MagicMock()
        on_terminal = MagicMock()
        on_restart = MagicMock()

        merged: dict[str, object] = {
            "goal_provider": goal_provider,
            "on_goal_terminal": on_terminal,
            "on_loop_restart": on_restart,
            "file_content_reader": lambda _fid: b"",
            "keep": "value",
        }

        stripped = pop_checkpoint_incompatible_merged_context(merged)

        assert set(stripped.keys()) == {
            "goal_provider",
            "on_goal_terminal",
            "on_loop_restart",
            "file_content_reader",
        }
        assert merged == {"keep": "value"}
        assert stripped["goal_provider"] is goal_provider


class TestRunAgentLoopModelSlugSource:
    """run_agent_loop resolves the primary model slug from the agent LLM.

    AgentRuntimeConfig has no ``llm`` field, so the slug comes from ``agent_state.llm``.
    The access is via ``getattr`` so custom LLM objects that omit ``model_name``
    (e.g. test fakes) degrade gracefully instead of raising.
    """

    def test_model_slug_reads_from_agent_llm_not_config(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        # Compare signatures rebuilt from the AST so quote style and line wrapping
        # in the module under test cannot invalidate this guard.
        tree = ast.parse(source)
        calls = {ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        attributes = {ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert "parse_route_model_id(llm_model or '')" in calls
        assert "getattr(agent_state.llm, 'model_name', None)" in calls
        assert "agent_state.config.llm" not in attributes


class TestRunAgentLoopRoundBudget:
    """One round budget feeds the graph's step limit, the guards, and the goal continuation of a run."""

    def test_graph_guards_and_stream_context_share_the_runs_round_budget(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        calls = {ast.unparse(node) for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)}

        def keywords(callee: str) -> set[str]:
            return {
                f"{kw.arg}={ast.unparse(kw.value)}"
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Call) and ast.unparse(node.func) == callee
                for kw in node.keywords
            }

        assert "effective_round_budget(getattr(agent_state, 'config', None))" in calls
        assert "graph_recursion_limit(round_budget, agent_state._agent)" in calls
        assert "round_budget=round_budget" in keywords("reset_all_guards")
        assert "round_budget=round_budget" in keywords("StreamContext")

    def test_the_session_is_bound_before_the_guards_are_reset(self) -> None:
        """A run finds its own session's guard, and a resume finds its own window, only if the session is bound first."""
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")
        run_agent_loop = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_agent_loop"
        )

        def first_call_line(callee: str) -> int:
            return min(
                node.lineno
                for node in ast.walk(run_agent_loop)
                if isinstance(node, ast.Call) and ast.unparse(node.func) == callee
            )

        assert first_call_line("set_approval_session") < first_call_line("reset_all_guards")


class TestRunAgentLoopOuterErrorFaultSide:
    """The outer-loop error_event carries the deterministic fault side and recovery actions,
    so the GUI's trace timeline shows who owns the failure even when the executor loop itself raises."""

    def test_outer_error_event_attributes_fault_side(self) -> None:
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[3] / "src/myrm_agent_harness/agent/_internals/agent_runtime.py"
        ).read_text(encoding="utf-8")

        def calls() -> set[str]:
            """Call signatures rebuilt from the AST, so line wrapping is irrelevant."""
            return {ast.unparse(node) for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call)}

        signatures = calls()
        # fault_side must be computed via the pure-rules classifier, not guessed.
        assert "classify_fault_side(error_kind=error_kind.value)" in signatures
        # When error_kind is UNKNOWN, the diagnostic error_type refines the
        # attribution (unified classifier falls back error_kind → error_type).
        refined = [sig for sig in signatures if sig.startswith("classify_fault_side(") and "error_type" in sig]
        assert refined, "no classify_fault_side call passes error_type for diagnostic refinement"
        assert any("error_type=diagnostic_type" in sig for sig in refined)
        # recovery_actions must be generated when a diagnostic payload exists.
        assert any(sig.startswith("LLMErrorDiagnostic.get_recovery_actions(") for sig in signatures)
        # The outer-loop error_event must be persisted to the event journal
        # (transport-only fields stripped) so trace reconstruction sees fatal
        # errors raised outside the executor.
        assert "event_logger.log(AgentEventType.ERROR.value, persisted)" in signatures
        assert "persisted.pop('type', None)" in signatures
        assert "persisted.pop('messageId', None)" in signatures


class TestEffectiveRoundBudget:
    """The graph and its guards read one budget, and an explicit setting is honoured."""

    def test_explicit_budget_is_counted_two_steps_a_round(self) -> None:
        """Raising a configured budget would override what the operator asked for.

        ``AgentConfig.from_env`` maps ``MYRM_RECURSION_LIMIT`` onto ``recursion_limit`` and the builders map
        ``max_iterations * 2`` and ``max_turns * 2``: the steps of a bare model/tools loop, two a round.
        """
        from myrm_agent_harness.agent._internals._agent_helpers import effective_round_budget

        for configured, rounds in ((2, 1), (3, 1), (20, 10), (50, 25), (100, 50), (300, 150), (1000, 500)):
            assert effective_round_budget(MagicMock(recursion_limit=configured)) == rounds

    def test_missing_budget_falls_back_to_a_workable_default(self) -> None:
        from myrm_agent_harness.agent._internals._agent_helpers import effective_round_budget

        assert effective_round_budget(MagicMock(recursion_limit=None)) == 150
        assert effective_round_budget(MagicMock(recursion_limit=0)) == 150
        assert effective_round_budget(MagicMock(recursion_limit=-5)) == 150
        assert effective_round_budget(None) == 150
        assert effective_round_budget(MagicMock()) == 150

    def test_guards_are_tuned_to_the_rounds_the_graph_is_given(self) -> None:
        """A guard tuned to a smaller number would fire its thresholds proportionally early."""
        from myrm_agent_harness.agent._internals._agent_helpers import effective_round_budget
        from myrm_agent_harness.agent.security.guards.loop_guard.guard import LoopGuard

        rounds = effective_round_budget(MagicMock(recursion_limit=100))
        guard = LoopGuard(round_budget=rounds)
        assert guard._budget_critical == rounds * 9 // 10
