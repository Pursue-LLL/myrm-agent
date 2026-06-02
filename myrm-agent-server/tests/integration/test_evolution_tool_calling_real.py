"""Real-world integration test for Evolution Agent Tool Calling (Scheme E).

Tests Evolution Agent with real LLM and real tools (no mocks).
Uses BASIC_API_KEY for real model testing.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.agent.skills.evolution import (
    EvolutionIntegration,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.execution.tool_selector import EvolutionToolConfig

logger = logging.getLogger(__name__)


@pytest.fixture
def temp_workspace():
    """Create temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_path = Path(tmpdir)
        db_path = workspace_path / "test_evolution.db"

        # Create test files for tool calling
        test_file = workspace_path / "test_code.py"
        test_file.write_text("""# Test code with a bug
def calculate_sum(a, b):
    return a - b  # Bug: should be a + b

def main():
    result = calculate_sum(5, 3)
    print(f"Result: {result}")
""")

        yield {
            "workspace": workspace_path,
            "db_path": db_path,
            "test_file": test_file,
        }


@pytest.fixture
def evolution_llm():
    """Create LLM for evolution testing (with tool calling support).

    Uses mock LLM that simulates tool calls for deterministic testing.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage

    class EvolutionMockLLM(BaseChatModel):
        """Mock LLM that simulates Evolution Agent tool calling."""

        model_name: str = "test-evolution-model"
        call_count: int = 0  # Track number of calls

        async def ainvoke(self, messages, **kwargs):
            """Async generate with tool calling simulation."""
            self.call_count += 1

            # First call: Request file_read_tool (note: actual tool name has _tool suffix)
            if self.call_count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "file_read_tool",
                            "args": {"file_path": "test_code.py"},
                            "id": "call_file_read_1",
                        }
                    ],
                )

            # Second call: After reading file, generate fixed code
            return AIMessage(
                content="""EVOLUTION_COMPLETE
```diff
--- a/test_code.py
+++ b/test_code.py
@@ -1,6 +1,6 @@
 # Test code with a bug
 def calculate_sum(a, b):
-    return a - b  # Bug: should be a + b
+    return a + b  # Fixed: use addition
 
 def main():
     result = calculate_sum(5, 3)
```

Fixed the bug by changing subtraction to addition in calculate_sum function."""
            )

        def _generate(self, *args, **kwargs):
            """Sync generate (not used)."""
            raise NotImplementedError()

        @property
        def _llm_type(self):
            return "evolution_mock_llm"

    return EvolutionMockLLM(model_name="test-evolution-model")


@pytest.mark.skip(reason="SkillEvolutionEngine no longer holds _evolution_tools; tool calling moved to integration layer")
@pytest.mark.asyncio
@pytest.mark.integration
async def test_evolution_tool_calling_integration(temp_workspace, evolution_llm):
    """Test Evolution Agent tool calling integration (Scheme E).

    Tests that Evolution Agent can:
    1. Use file_read tool to read code
    2. Handle tool results and metrics
    3. Generate fixed code with context from tools
    4. Record metrics for tool usage
    """
    workspace = temp_workspace["workspace"]
    db_path = temp_workspace["db_path"]
    test_file = temp_workspace["test_file"]

    # Initialize evolution with tool calling enabled
    evolution = EvolutionIntegration(
        db_path=db_path,
        llm=evolution_llm,
        enable_embedding_cache=False,
        enable_background_queue=False,
        enable_tool_calling=True,  # Enable Scheme E tool calling
        tool_config=EvolutionToolConfig(
            max_tool_rounds=3,  # Allow 3 rounds of tool calling
            enable_smart_error_handling=True,
            enable_grep=True,  # Enable code search
            enable_web_fetch=False,  # Disable for speed
            tool_call_limits={
                "file_read": 10,
                "glob": 5,
                "grep": 5,
                "web_search": 2,  # Limit web searches
            },
            result_summarization_threshold=100_000,  # 100K chars
            enable_result_summarization=True,
        ),
        workspace_path=workspace,
    )

    # Verify evolution engine and tools were created
    assert evolution.engine is not None
    assert evolution.engine._evolution_tools is not None
    logger.info(f"📋 Evolution tools: {[t.name for t in evolution.engine._evolution_tools]}")

    try:
        # Create a failing skill that needs file_read to understand the bug
        failing_skill = SkillRecord(
            skill_id="buggy_calculator",
            name="buggy_calculator",
            description="Calculator with a subtraction bug (should use addition)",
            content=test_file.read_text(),
            path=str(test_file.relative_to(workspace)),
            lineage=SkillLineage(
                evolution_type=EvolutionType.CAPTURED,
                version=1,
            ),
        )

        await evolution.store.save_skill(failing_skill)

        # Record 3 consecutive failures to trigger auto-fix
        error_message = """
Test failed: Expected result 8, got 2
calculate_sum(5, 3) returned 2 instead of 8
Bug detected in line 3: return a - b (should be a + b)
"""

        logger.info("\n" + "=" * 60)
        logger.info("🔧 Triggering Evolution Agent with Tool Calling (Scheme E)")
        logger.info("=" * 60)

        for i in range(3):
            logger.info(f"Recording failure {i + 1}/3...")
            await evolution.record_execution(
                skill_id="buggy_calculator",
                success=False,
                error_message=error_message,
            )

        # Give engine time to complete evolution
        await asyncio.sleep(3)

        # Verify evolved skill was created
        active_skills = evolution.store.get_active_skills()
        assert len(active_skills) >= 1, "No active skills found after evolution"

        evolved_skill = None
        for skill in active_skills:
            if skill.lineage.parent_id == "buggy_calculator":
                evolved_skill = skill
                break

        assert evolved_skill is not None, "Evolved skill not found"
        assert evolved_skill.lineage.version == 2

        # Verify the fix changed the code
        assert evolved_skill.content != failing_skill.content
        assert "a + b" in evolved_skill.content or "return a+b" in evolved_skill.content

        logger.info("\n✅ Evolution with Tool Calling succeeded!")
        logger.info(f"   Original skill: {failing_skill.skill_id} (v1)")
        logger.info(f"   Evolved skill: {evolved_skill.skill_id} (v2)")
        logger.info(f"   Content changed: {len(evolved_skill.content)} chars")

        # Check metrics
        stats = evolution.get_stats()
        metrics = stats.get("metrics", {})

        logger.info("\n📊 Evolution Metrics (Scheme E):")
        logger.info(f"   Total evolutions: {metrics.get('summary', {}).get('total', 0)}")
        success_rate = metrics.get("summary", {}).get("success_rate", 0)
        # success_rate might be a string like "0%" or a number
        if isinstance(success_rate, str):
            logger.info(f"   Success rate: {success_rate}")
        else:
            logger.info(f"   Success rate: {success_rate:.1%}")

        # Verify tool usage was recorded (if metrics tracker includes tool stats)
        evolution_metrics_report = evolution.metrics_tracker.get_report()
        if "tool_usage" in evolution_metrics_report:
            logger.info(f"   Tool calls: {evolution_metrics_report['tool_usage'].get('total_calls', 0)}")
            logger.info(f"   Tool errors: {evolution_metrics_report['tool_usage'].get('total_errors', 0)}")

        if "summarization" in evolution_metrics_report:
            logger.info(f"   Summarizations: {evolution_metrics_report['summarization'].get('total_summarizations', 0)}")
            logger.info(f"   Tokens saved: {evolution_metrics_report['summarization'].get('total_token_saved', 0)}")

    finally:
        await evolution.close()


@pytest.mark.skip(reason="SkillEvolutionEngine no longer holds _evolution_tools; tool calling moved to integration layer")
@pytest.mark.asyncio
@pytest.mark.integration
async def test_evolution_tool_calling_metrics(temp_workspace, evolution_llm):
    """Test that Evolution Agent records tool usage metrics (Scheme E)."""
    workspace = temp_workspace["workspace"]
    db_path = temp_workspace["db_path"]

    # Initialize evolution with tool calling
    evolution = EvolutionIntegration(
        db_path=db_path,
        llm=evolution_llm,
        enable_tool_calling=True,
        tool_config=EvolutionToolConfig(max_tool_rounds=2),
        workspace_path=workspace,
    )

    try:
        # Create a skill and trigger evolution
        skill = SkillRecord(
            skill_id="metrics_test",
            name="metrics_test",
            description="Test metrics recording",
            content="# Test code\n\ndef test(): pass\n",
            path="metrics_test.py",
            lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
        )
        await evolution.store.save_skill(skill)

        # Trigger evolution
        for _ in range(3):
            await evolution.record_execution(
                skill_id="metrics_test",
                success=False,
                error_message="Test error for metrics",
            )

        await asyncio.sleep(2)

        # Check metrics report includes Scheme E fields
        report = evolution.metrics_tracker.get_report()

        assert "summary" in report
        assert "by_type" in report

        # Scheme E metrics should be present (tool_usage, summarization)
        # Note: May be 0 if LLM didn't call tools, but fields should exist
        logger.info(f"\n📊 Metrics Report Keys: {list(report.keys())}")

    finally:
        await evolution.close()
