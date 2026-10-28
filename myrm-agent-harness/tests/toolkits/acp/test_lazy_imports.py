"""Tests for the lazy import mechanism of the ACP packages."""

from __future__ import annotations

import pytest


class TestLazyImports:
    """Tests for ACP __init__.py lazy import mechanism."""

    def test_import_runtime_pool(self) -> None:
        from myrm_agent_harness.toolkits.acp import RuntimePool as PoolClass

        assert PoolClass is not None

    def test_import_runtime_config(self) -> None:
        from myrm_agent_harness.toolkits.acp import RuntimeConfig as CfgClass

        assert CfgClass is not None

    def test_import_runtime_backend(self) -> None:
        from myrm_agent_harness.toolkits.acp import RuntimeBackend as BackendProto

        assert BackendProto is not None

    def test_import_unknown_raises(self) -> None:
        import myrm_agent_harness.toolkits.acp as acp_mod

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = acp_mod.NonExistentThing  # type: ignore[attr-defined]

    def test_import_myrm_acp_server(self) -> None:
        from myrm_agent_harness.toolkits.acp import MyrmAcpServer

        assert MyrmAcpServer is not None

    def test_import_run_server(self) -> None:
        from myrm_agent_harness.toolkits.acp import run_server

        assert callable(run_server)

    def test_runtime_package_lazy_base_runtime(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime as runtime_pkg

        assert runtime_pkg.BaseRuntime is not None
        assert hasattr(runtime_pkg.BaseRuntime, "run_turn")

    def test_runtime_package_lazy_runtime_pool(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime as runtime_pkg

        assert runtime_pkg.RuntimePool is not None

    def test_runtime_package_unknown_raises(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime as runtime_pkg

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = runtime_pkg.NonExistentThing  # type: ignore[attr-defined]

    def test_acp_runtime_package_lazy_acp_runtime(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime.acp as acp_runtime_pkg
        from myrm_agent_harness.toolkits.acp.runtime.acp.runtime import AcpRuntime

        assert acp_runtime_pkg.AcpRuntime is AcpRuntime

    def test_acp_runtime_package_unknown_raises(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime.acp as acp_runtime_pkg

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = acp_runtime_pkg.NonExistentThing  # type: ignore[attr-defined]

    def test_cli_runtime_package_lazy_cli_runtime(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime.cli as cli_runtime_pkg
        from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime

        assert cli_runtime_pkg.CliRuntime is CliRuntime

    def test_cli_runtime_package_unknown_raises(self) -> None:
        import myrm_agent_harness.toolkits.acp.runtime.cli as cli_runtime_pkg

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = cli_runtime_pkg.NonExistentThing  # type: ignore[attr-defined]

    def test_server_package_lazy_myrm_acp_server(self) -> None:
        import myrm_agent_harness.toolkits.acp.server as server_pkg

        assert server_pkg.MyrmAcpServer is not None

    def test_server_package_lazy_run_server(self) -> None:
        import myrm_agent_harness.toolkits.acp.server as server_pkg

        assert callable(server_pkg.run_server)

    def test_server_package_lazy_agent_bridge(self) -> None:
        import myrm_agent_harness.toolkits.acp.server as server_pkg

        assert server_pkg.AgentBridge is not None
        assert server_pkg.AgentFactory is not None

    def test_server_package_unknown_raises(self) -> None:
        import myrm_agent_harness.toolkits.acp.server as server_pkg

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = server_pkg.NonExistentThing  # type: ignore[attr-defined]


class TestAcpToolsImport:
    """Tests for acp_tools.py module imports."""

    def test_import_acp_tools(self) -> None:
        from myrm_agent_harness.toolkits.acp import (
            MyrmAcpServer,
            RuntimeBackend,
            RuntimeConfig,
            RuntimePool,
            run_server,
        )

        assert RuntimePool is not None
        assert MyrmAcpServer is not None
        assert RuntimeConfig is not None
        assert RuntimeBackend is not None
        assert callable(run_server)
