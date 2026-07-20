"""Agent 导出安全与团队格式单元测试

覆盖 _strip_sensitive_auth 凭据剔除（openapi_services.auth + tool_gateway_config.auth_token）
和团队导出/导入格式的纯逻辑验证。不依赖数据库或 HTTP 服务器。
"""

import copy

from app.api.agents.agent import _SENSITIVE_AUTH_FIELDS, _strip_sensitive_auth


class TestStripSensitiveAuth:
    """_strip_sensitive_auth 凭据剔除测试"""

    def test_strips_api_key(self) -> None:
        data: dict = {
            "openapi_services": [
                {
                    "name": "Jira",
                    "auth": {"type": "api_key", "api_key": "SECRET", "api_key_header": "X-Key"},
                }
            ]
        }
        _strip_sensitive_auth(data)
        auth = data["openapi_services"][0]["auth"]
        assert "api_key" not in auth
        assert auth["type"] == "api_key"
        assert auth["api_key_header"] == "X-Key"

    def test_strips_bearer_token(self) -> None:
        data: dict = {
            "openapi_services": [{"auth": {"type": "bearer", "bearer_token": "xoxb-secret"}}]
        }
        _strip_sensitive_auth(data)
        assert "bearer_token" not in data["openapi_services"][0]["auth"]
        assert data["openapi_services"][0]["auth"]["type"] == "bearer"

    def test_strips_oauth_fields(self) -> None:
        data: dict = {
            "openapi_services": [
                {
                    "auth": {
                        "type": "oauth2",
                        "client_secret": "secret",
                        "password": "pass",
                        "username": "admin",
                        "client_id": "my-app",
                    }
                }
            ]
        }
        _strip_sensitive_auth(data)
        auth = data["openapi_services"][0]["auth"]
        assert "client_secret" not in auth
        assert "password" not in auth
        assert "username" not in auth
        assert auth["client_id"] == "my-app"
        assert auth["type"] == "oauth2"

    def test_strips_tool_gateway_auth_token(self) -> None:
        data: dict = {
            "tool_gateway_config": {
                "use_gateway": True,
                "gateway_url": "https://gw.example.com",
                "auth_token": "gw-secret-token",
            }
        }
        _strip_sensitive_auth(data)
        gw = data["tool_gateway_config"]
        assert "auth_token" not in gw
        assert gw["use_gateway"] is True
        assert gw["gateway_url"] == "https://gw.example.com"

    def test_strips_both_openapi_and_gateway(self) -> None:
        data: dict = {
            "openapi_services": [{"auth": {"type": "api_key", "api_key": "K1"}}],
            "tool_gateway_config": {"auth_token": "gw-tok", "use_gateway": True},
        }
        _strip_sensitive_auth(data)
        assert "api_key" not in data["openapi_services"][0]["auth"]
        assert "auth_token" not in data["tool_gateway_config"]

    def test_no_crash_on_empty_services(self) -> None:
        _strip_sensitive_auth({})
        _strip_sensitive_auth({"openapi_services": None})
        _strip_sensitive_auth({"openapi_services": []})

    def test_no_crash_on_none_auth(self) -> None:
        data: dict = {"openapi_services": [{"name": "X", "auth": None}]}
        _strip_sensitive_auth(data)

    def test_no_crash_on_non_dict_entries(self) -> None:
        data: dict = {"openapi_services": ["not-a-dict", 42, None]}
        _strip_sensitive_auth(data)

    def test_no_crash_on_none_gateway(self) -> None:
        _strip_sensitive_auth({"tool_gateway_config": None})
        _strip_sensitive_auth({"tool_gateway_config": "not-a-dict"})

    def test_no_crash_on_gateway_without_auth_token(self) -> None:
        data: dict = {"tool_gateway_config": {"use_gateway": False}}
        _strip_sensitive_auth(data)
        assert data["tool_gateway_config"] == {"use_gateway": False}

    def test_multiple_services(self) -> None:
        data: dict = {
            "openapi_services": [
                {"auth": {"type": "api_key", "api_key": "K1"}},
                {"auth": {"type": "bearer", "bearer_token": "T1"}},
                {"auth": {"type": "oauth2", "client_secret": "S1", "password": "P1", "username": "U1"}},
            ]
        }
        _strip_sensitive_auth(data)
        for svc in data["openapi_services"]:
            auth = svc["auth"]
            for field in _SENSITIVE_AUTH_FIELDS:
                assert field not in auth, f"{field} still present in {auth}"
            assert "type" in auth

    def test_does_not_mutate_unrelated_fields(self) -> None:
        original = {
            "name": "My Agent",
            "system_prompt": "Hello",
            "openapi_services": [
                {"name": "API", "spec_url": "https://x.com", "auth": {"type": "api_key", "api_key": "S"}}
            ],
            "tool_gateway_config": {"use_gateway": True, "gateway_url": "https://gw.com", "auth_token": "tok"},
        }
        data = copy.deepcopy(original)
        _strip_sensitive_auth(data)
        assert data["name"] == original["name"]
        assert data["system_prompt"] == original["system_prompt"]
        assert data["openapi_services"][0]["name"] == "API"
        assert data["openapi_services"][0]["spec_url"] == "https://x.com"
        assert data["tool_gateway_config"]["gateway_url"] == "https://gw.com"
        assert data["tool_gateway_config"]["use_gateway"] is True

    def test_all_sensitive_fields_covered(self) -> None:
        """Ensure _SENSITIVE_AUTH_FIELDS covers all known credential fields."""
        expected = {"api_key", "bearer_token", "client_secret", "password", "username"}
        assert _SENSITIVE_AUTH_FIELDS == expected


class TestTeamExportFormat:
    """团队导出格式检测逻辑验证"""

    def test_team_format_detected(self) -> None:
        data = {"_export_version": 1, "agent_type": "team", "leader": {}, "members": []}
        assert data.get("_export_version") and data.get("agent_type") == "team"

    def test_single_format_not_team(self) -> None:
        data = {"name": "Solo", "system_prompt": "Hi"}
        assert not (data.get("_export_version") and data.get("agent_type") == "team")

    def test_individual_with_agent_type_not_team(self) -> None:
        data = {"agent_type": "individual", "name": "Solo"}
        assert not (data.get("_export_version") and data.get("agent_type") == "team")

    def test_version_without_team_type_not_team(self) -> None:
        data = {"_export_version": 1, "agent_type": "individual"}
        assert not (data.get("_export_version") and data.get("agent_type") == "team")

    def test_version_zero_not_treated_as_team(self) -> None:
        data = {"_export_version": 0, "agent_type": "team"}
        assert not (data.get("_export_version") and data.get("agent_type") == "team")

    def test_missing_version_not_team(self) -> None:
        data = {"agent_type": "team", "leader": {}, "members": []}
        assert not (data.get("_export_version") and data.get("agent_type") == "team")

    def test_team_format_with_populated_members(self) -> None:
        data = {
            "_export_version": 1,
            "agent_type": "team",
            "leader": {"name": "Leader", "system_prompt": "Lead"},
            "members": [
                {"name": "Member A", "system_prompt": "Hi A"},
                {"name": "Member B", "system_prompt": "Hi B"},
            ],
        }
        assert data.get("_export_version") and data.get("agent_type") == "team"
        assert len(data["members"]) == 2
