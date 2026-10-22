"""自然语言单句插件安装、沙箱隔离依赖嗅探与零重启热重载全套自动化测试。

全面覆盖：
1. 自然语言意图解析与 GitHub/GitLab 仓库提取
2. SSRF、私网 IP (RFC 1918) 与云元数据强制防御拦截
3. 多模态依赖特征分级嗅探（MCP Server / Skill / Python / Node）与原生编译检测
4. AST 语法树与危险命令静态安全审计
5. 核心保留工具命名空间前缀隔离（防影子化劫持）
6. 事务级临时隔离构建、失败原子回滚与零残留物理卸载
7. 零重启热加载开关与智能体能力纪元（Capability Epoch）联动
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List, Tuple

import pytest
from myrm_agent_harness.agent.plugins.dependency_sniffer import (
    PluginProjectKind,
    SandboxDependencySniffer,
)
from myrm_agent_harness.agent.plugins.hot_reload_registry import (
    PluginHotReloadRegistry,
    PluginNotFoundError,
    PluginSecurityError,
    PluginStatus,
)
from myrm_agent_harness.agent.plugins.intent_parser import (
    InsecureRepoUrlError,
    RepoIntentParser,
    SafeRepoUrlValidator,
)
from myrm_agent_harness.agent.plugins.security_auditor import (
    PluginSecurityAuditor,
    ReservedToolGuard,
)


def test_repo_intent_parser_extracts_valid_install_command() -> None:
    """测试从自然语言对话中精准识别安装意图并提取 Git 仓库。"""
    parser = RepoIntentParser()

    user_prompt = "请帮我安装并使用 https://github.com/my-org/my-cool-tool 插件，谢谢！"
    result = parser.parse_install_intent(user_prompt)

    assert result.is_install_intent is True
    assert result.target is not None
    assert result.target.owner == "my-org"
    assert result.target.repo == "my-cool-tool"
    assert result.target.normalized_url == "https://github.com/my-org/my-cool-tool"


def test_repo_intent_parser_rejects_missing_keywords_or_invalid_url() -> None:
    """测试缺少安装意图关键词或非法链接时的安全拒止。"""
    parser = RepoIntentParser()

    # 有链接但无安装动作意图
    result_no_intent = parser.parse_install_intent(
        "昨天我浏览了 https://github.com/my-org/my-cool-tool 这个仓库，感觉很酷。"
    )
    assert result_no_intent.is_install_intent is False
    assert result_no_intent.target is None

    # 完全没有链接
    result_no_url = parser.parse_install_intent("帮我安装一个天气查询插件")
    assert result_no_url.is_install_intent is False


def test_safe_repo_url_validator_ssrf_and_dns_protection() -> None:
    """测试对私网 IP、本地回环、AWS 元数据以及非开源白名单域名的强制阻断。"""
    # 阻断私网 IP 与 Localhost
    with pytest.raises(InsecureRepoUrlError, match="Loopback or private network"):
        SafeRepoUrlValidator.validate_and_parse("https://127.0.0.1/evil/tool")

    with pytest.raises(InsecureRepoUrlError, match="Loopback or private network"):
        SafeRepoUrlValidator.validate_and_parse("https://192.168.1.10/evil/tool")

    # 阻断云元数据 IP
    with pytest.raises(InsecureRepoUrlError, match="Loopback or private network"):
        SafeRepoUrlValidator.validate_and_parse("https://169.254.169.254/latest/meta-data")

    # 阻断非代码托管白名单
    with pytest.raises(InsecureRepoUrlError, match="Host 'evil-hacker.com' is not in allowed"):
        SafeRepoUrlValidator.validate_and_parse("https://evil-hacker.com/malware/repo")

    # 阻断非 HTTPS 协议
    with pytest.raises(InsecureRepoUrlError, match="Scheme 'http' is insecure"):
        SafeRepoUrlValidator.validate_and_parse("http://github.com/org/repo")


def test_sandbox_dependency_sniffer_priority_and_native_extensions() -> None:
    """测试分级嗅探管道优先级（MCP -> Skill -> Python -> Node）及原生编译识别。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # 1. 模拟 MCP 优先
        mcp_file = root / "mcp.json"
        mcp_file.write_text(json.dumps({"mcpServers": {"test_srv": {}}}), encoding="utf-8")
        py_file = root / "setup.py"
        py_file.write_text("# python setup", encoding="utf-8")

        res_mcp = SandboxDependencySniffer.sniff_directory(root)
        assert res_mcp.kind == PluginProjectKind.MCP_SERVER
        assert res_mcp.manifest_file == "mcp.json"
        assert res_mcp.has_native_extensions is False

        # 2. 模拟原生编译文件检测
        c_file = root / "native.cpp"
        c_file.write_text("// C++ code", encoding="utf-8")
        assert SandboxDependencySniffer.check_has_native_extensions(root) is True


def test_plugin_security_auditor_detects_eval_exec_and_malicious_commands() -> None:
    """测试 AST 语法树动态调用分析与高危危险命令正则拦截。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)

        # 正常纯净代码
        clean_file = root / "safe.py"
        clean_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        clean_report = PluginSecurityAuditor.audit_directory(root)
        assert clean_report.is_clean is True
        assert len(clean_report.detected_risks) == 0

        # 注入动态 eval
        eval_file = root / "eval_danger.py"
        eval_file.write_text("eval('print(123)')\n", encoding="utf-8")
        danger_report_1 = PluginSecurityAuditor.audit_directory(root)
        assert danger_report_1.is_clean is False
        assert any("eval()" in risk for risk in danger_report_1.detected_risks)
        eval_file.unlink()

        # 注入危险 shell 提权破坏命令
        sh_file = root / "deploy.sh"
        sh_file.write_text("rm -rf / \n", encoding="utf-8")
        danger_report_2 = PluginSecurityAuditor.audit_directory(root)
        assert danger_report_2.is_clean is False
        assert any("rm -rf /" in risk for risk in danger_report_2.detected_risks)


def test_reserved_tool_guard_namespace_isolation() -> None:
    """测试核心系统保留字工具自动被添加命名空间前缀，防影子化劫持。"""
    tools = ["bash", "my_custom_tool", "write_file", "calculate"]
    plugin_id = "plug_myorg_mytool"

    sanitized = ReservedToolGuard.sanitize_plugin_tool_names(plugin_id, tools)

    assert sanitized == (
        "plug_myorg_mytool__bash",
        "my_custom_tool",
        "plug_myorg_mytool__write_file",
        "calculate",
    )


def test_hot_reload_registry_staging_rollback_on_audit_failure() -> None:
    """测试事务级 Staging 临时隔离构建：审计失败时原子回滚，不污染生产目录。"""
    with tempfile.TemporaryDirectory() as base_tmp:
        base_dir = Path(base_tmp)
        plugins_root = base_dir / "installed_plugins"
        mock_source = base_dir / "source_repo"
        mock_source.mkdir()

        # 故意写入危险代码
        bad_code = mock_source / "danger.py"
        bad_code.write_text("exec('import os; os.system(1)')", encoding="utf-8")

        registry = PluginHotReloadRegistry(plugins_root_dir=plugins_root)

        with pytest.raises(PluginSecurityError, match="Security audit rejected plugin"):
            registry.install_from_repository(
                repo_url="https://github.com/hacker-team/malicious-agent",
                source_dir=mock_source,
            )

        # 验证生产插件目录完全没有该插件残余
        assert not (plugins_root / "plug_hacker_team_malicious_agent").exists()
        assert len(registry.list_plugins()) == 0


def test_hot_reload_registry_full_lifecycle_and_epoch_notification() -> None:
    """测试插件安装、状态切换、动态工具导出、零残留卸载与纪元通知全生命周期闭环。"""
    notified_epochs: List[int] = []

    def on_change() -> None:
        notified_epochs.append(len(notified_epochs) + 1)

    with tempfile.TemporaryDirectory() as base_tmp:
        base_dir = Path(base_tmp)
        plugins_root = base_dir / "installed_plugins"
        mock_source = base_dir / "source_repo"
        mock_source.mkdir()

        # 构造合规的 MCP 插件
        mcp_json = mock_source / "mcp.json"
        mcp_json.write_text(
            json.dumps({"mcpServers": {"web_search_server": {"command": "node"}}}),
            encoding="utf-8",
        )
        safe_py = mock_source / "plugin.py"
        safe_py.write_text("def run(): pass\n", encoding="utf-8")

        registry = PluginHotReloadRegistry(
            plugins_root_dir=plugins_root,
            on_capability_changed=on_change,
        )

        # 1. 成功安装并激活
        repo_url = "https://github.com/org-safe/web-search-plugin"
        metadata = registry.install_from_repository(repo_url=repo_url, source_dir=mock_source)

        assert metadata.status == PluginStatus.ACTIVE
        assert metadata.project_kind == PluginProjectKind.MCP_SERVER
        assert len(notified_epochs) == 1
        assert metadata.install_dir.exists()

        # 工具集包含嗅探到的清单
        active_tools: Tuple[str, ...] = registry.get_active_tools()
        assert "mcp.json" in active_tools

        # 2. 切换为 INACTIVE
        updated = registry.toggle_plugin(metadata.plugin_id, enable=False)
        assert updated.status == PluginStatus.INACTIVE
        assert len(notified_epochs) == 2
        assert len(registry.get_active_tools()) == 0

        # 3. 恢复为 ACTIVE
        updated_again = registry.toggle_plugin(metadata.plugin_id, enable=True)
        assert updated_again.status == PluginStatus.ACTIVE
        assert len(notified_epochs) == 3
        assert len(registry.get_active_tools()) > 0

        # 4. 零残留物理卸载
        registry.uninstall_plugin(metadata.plugin_id)
        assert len(notified_epochs) == 4
        assert not metadata.install_dir.exists()
        assert len(registry.list_plugins()) == 0

        # 再次查找应抛出 PluginNotFoundError
        with pytest.raises(PluginNotFoundError):
            registry.get_plugin(metadata.plugin_id)
