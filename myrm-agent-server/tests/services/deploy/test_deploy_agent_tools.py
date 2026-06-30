"""Tests for the deploy agent tool (server business layer).

Covers:
- DeployBackend Protocol contract
- DeployResult dataclass
- create_deploy_tool factory
- Tool behavior: preflight failure, user denial, deploy success, deploy error
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.deploy.deploy_agent_tools import DeployBackend, DeployResult, create_deploy_tool


class FakeDeployBackend:
    """Test double implementing DeployBackend."""

    def __init__(
        self,
        *,
        preflight_ok: bool = True,
        preflight_msg: str = "Ready",
        deploy_result: DeployResult | None = None,
        deploy_error: Exception | None = None,
        artifact_name: str | None = "Test Page",
    ):
        self._preflight_ok = preflight_ok
        self._preflight_msg = preflight_msg
        self._deploy_result = deploy_result or DeployResult(
            success=True,
            url="https://test.vercel.app",
            deployment_id="dpl_abc123",
            project_id="prj_xyz",
            status="READY",
        )
        self._deploy_error = deploy_error
        self._artifact_name = artifact_name

    async def preflight(self, artifact_id: str) -> tuple[bool, str]:
        return self._preflight_ok, self._preflight_msg

    async def execute_deploy(self, artifact_id: str) -> DeployResult:
        if self._deploy_error:
            raise self._deploy_error
        return self._deploy_result

    async def get_artifact_name(self, artifact_id: str) -> str | None:
        return self._artifact_name


class TestDeployBackendProtocol:
    def test_fake_backend_is_deploy_backend(self) -> None:
        backend = FakeDeployBackend()
        assert isinstance(backend, DeployBackend)

    def test_class_without_methods_is_not_deploy_backend(self) -> None:
        class NotABackend:
            pass

        assert not isinstance(NotABackend(), DeployBackend)


class TestDeployResult:
    def test_success_result(self) -> None:
        result = DeployResult(
            success=True,
            url="https://test.vercel.app",
            deployment_id="dpl_1",
            project_id="prj_1",
            status="READY",
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self) -> None:
        result = DeployResult(
            success=False,
            url="",
            deployment_id="",
            project_id="",
            status="ERROR",
            error="Token missing",
        )
        assert result.success is False
        assert result.error == "Token missing"

    def test_frozen(self) -> None:
        result = DeployResult(success=True, url="x", deployment_id="", project_id="", status="OK")
        with pytest.raises(AttributeError):
            result.url = "y"  # type: ignore[misc]


class TestCreateDeployTool:
    def test_factory_returns_single_tool(self) -> None:
        backend = FakeDeployBackend()
        tools = create_deploy_tool(backend)
        assert len(tools) == 1
        assert tools[0].name == "deploy_artifact"

    def test_tool_has_description(self) -> None:
        backend = FakeDeployBackend()
        tools = create_deploy_tool(backend)
        assert "deploy" in tools[0].description.lower()


class TestDeployToolExecution:
    @pytest.mark.asyncio
    async def test_preflight_failure_returns_message(self) -> None:
        backend = FakeDeployBackend(preflight_ok=False, preflight_msg="No versions to deploy.")
        tool = create_deploy_tool(backend)[0]
        result = await tool.ainvoke({"artifact_id": "art_001"})
        assert "Cannot deploy" in result
        assert "No versions to deploy" in result

    @pytest.mark.asyncio
    async def test_user_denial_returns_cancelled(self) -> None:
        backend = FakeDeployBackend()
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "deny"}
            result = await tool.ainvoke({"artifact_id": "art_002"})
        assert "cancelled" in result.lower()

    @pytest.mark.asyncio
    async def test_decisions_reject_format_denied(self) -> None:
        backend = FakeDeployBackend()
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decisions": [{"type": "reject"}]}
            result = await tool.ainvoke({"artifact_id": "art_reject"})
        assert "cancelled" in result.lower()

    @pytest.mark.asyncio
    async def test_successful_deploy(self) -> None:
        backend = FakeDeployBackend()
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "approve"}
            result = await tool.ainvoke({"artifact_id": "art_003"})
        assert "https://test.vercel.app" in result
        assert "success" in result

    @pytest.mark.asyncio
    async def test_deploy_exception_handled(self) -> None:
        backend = FakeDeployBackend(deploy_error=RuntimeError("Vercel API timeout"))
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "approve"}
            result = await tool.ainvoke({"artifact_id": "art_004"})
        assert "Deployment failed" in result
        assert "Vercel API timeout" in result

    @pytest.mark.asyncio
    async def test_deploy_failure_result(self) -> None:
        backend = FakeDeployBackend(
            deploy_result=DeployResult(
                success=False,
                url="",
                deployment_id="",
                project_id="",
                status="PREFLIGHT_FAILED",
                error="Empty payload",
            ),
        )
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "approve"}
            result = await tool.ainvoke({"artifact_id": "art_005"})
        assert "Deployment failed" in result
        assert "Empty payload" in result

    @pytest.mark.asyncio
    async def test_null_response_treated_as_denial(self) -> None:
        backend = FakeDeployBackend()
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = None
            result = await tool.ainvoke({"artifact_id": "art_006"})
        assert "cancelled" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_artifact_uses_id_prefix(self) -> None:
        backend = FakeDeployBackend(artifact_name=None, preflight_ok=False, preflight_msg="not found")
        tool = create_deploy_tool(backend)[0]
        result = await tool.ainvoke({"artifact_id": "abcd1234-full-id"})
        assert "abcd1234" in result

    @pytest.mark.asyncio
    async def test_string_approval_proceeds_to_deploy(self) -> None:
        backend = FakeDeployBackend()
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "approved"
            result = await tool.ainvoke({"artifact_id": "art_str"})
        assert "success" in result
        assert "https://test.vercel.app" in result

    @pytest.mark.asyncio
    async def test_failure_without_error_uses_status(self) -> None:
        backend = FakeDeployBackend(
            deploy_result=DeployResult(
                success=False,
                url="",
                deployment_id="",
                project_id="",
                status="QUOTA_EXCEEDED",
                error=None,
            ),
        )
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "approve"}
            result = await tool.ainvoke({"artifact_id": "art_quota"})
        assert "QUOTA_EXCEEDED" in result

    @pytest.mark.asyncio
    async def test_approval_payload_contains_required_fields(self) -> None:
        backend = FakeDeployBackend(artifact_name="Dashboard")
        tool = create_deploy_tool(backend)[0]
        with patch("langgraph.types.interrupt") as mock_interrupt:
            mock_interrupt.return_value = {"decision": "deny"}
            await tool.ainvoke({"artifact_id": "art_payload"})

        payload = mock_interrupt.call_args[0][0]
        assert payload["action_type"] == "deploy_approval"
        assert payload["payload"]["artifact_id"] == "art_payload"
        assert payload["payload"]["artifact_name"] == "Dashboard"
        assert "Deploy" in payload["payload"]["message"]
