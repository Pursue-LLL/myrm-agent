"""Tests for SecurityPolicyExtension — custom PII fields passthrough."""

from app.ai_agents.extensions.security_policy_extension import SecurityPolicyExtension


class TestCustomPiiFieldsInit:
    """Verify custom PII fields are correctly stored as tuples."""

    def test_custom_fields_converted_to_tuples(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=True,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
            privacy_custom_keywords_s2=["secret", "internal"],
            privacy_custom_keywords_s3=["topsecret"],
            privacy_custom_patterns_s2=[r"PROJ-\d{4}"],
            privacy_custom_patterns_s3=[r"EMP-\d{6}"],
            privacy_sensitive_tools_s2=["shell_exec"],
            privacy_sensitive_tools_s3=["browser_navigate_tool"],
        )
        assert ext.privacy_custom_keywords_s2 == ("secret", "internal")
        assert ext.privacy_custom_keywords_s3 == ("topsecret",)
        assert ext.privacy_custom_patterns_s2 == (r"PROJ-\d{4}",)
        assert ext.privacy_custom_patterns_s3 == (r"EMP-\d{6}",)
        assert ext.privacy_sensitive_tools_s2 == ("shell_exec",)
        assert ext.privacy_sensitive_tools_s3 == ("browser_navigate_tool",)

    def test_none_defaults_to_empty_tuples(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        assert ext.privacy_custom_keywords_s2 == ()
        assert ext.privacy_custom_keywords_s3 == ()
        assert ext.privacy_custom_patterns_s2 == ()
        assert ext.privacy_custom_patterns_s3 == ()
        assert ext.privacy_sensitive_tools_s2 == ()
        assert ext.privacy_sensitive_tools_s3 == ()

    def test_empty_list_yields_empty_tuple(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=True,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
            privacy_custom_keywords_s2=[],
            privacy_custom_patterns_s3=[],
        )
        assert ext.privacy_custom_keywords_s2 == ()
        assert ext.privacy_custom_patterns_s3 == ()


class TestAgentRequestCustomPiiFields:
    """Verify AgentRequest model accepts custom PII fields."""

    def test_agent_request_defaults_none(self):
        from app.services.agent.params.models import AgentRequest

        req = AgentRequest(messages=[], model="test", messageId="test-id")
        assert req.privacy_custom_keywords_s2 is None
        assert req.privacy_custom_keywords_s3 is None
        assert req.privacy_custom_patterns_s2 is None
        assert req.privacy_custom_patterns_s3 is None
        assert req.privacy_sensitive_tools_s2 is None
        assert req.privacy_sensitive_tools_s3 is None

    def test_agent_request_with_custom_fields(self):
        from app.services.agent.params.models import AgentRequest

        req = AgentRequest(
            messages=[],
            model="test",
            messageId="test-id",
            privacy_enabled=True,
            privacy_custom_keywords_s2=["secret"],
            privacy_custom_keywords_s3=["classified"],
            privacy_custom_patterns_s2=[r"\d{3}-\d{2}-\d{4}"],
            privacy_custom_patterns_s3=[r"EMP-\d+"],
            privacy_sensitive_tools_s2=["shell_exec"],
            privacy_sensitive_tools_s3=["browser_navigate_tool"],
        )
        assert req.privacy_custom_keywords_s2 == ["secret"]
        assert req.privacy_custom_keywords_s3 == ["classified"]
        assert req.privacy_custom_patterns_s2 == [r"\d{3}-\d{2}-\d{4}"]
        assert req.privacy_custom_patterns_s3 == [r"EMP-\d+"]
        assert req.privacy_sensitive_tools_s2 == ["shell_exec"]
        assert req.privacy_sensitive_tools_s3 == ["browser_navigate_tool"]


class TestExtensionName:
    def test_name(self):
        ext = SecurityPolicyExtension(
            privacy_enabled=False,
            privacy_s2_action="warn",
            privacy_s3_action="redact",
            channel_name="test",
            security_config_raw={},
            agent_security_raw={},
            declared_capabilities=[],
            declared_allowed_roots=[],
        )
        assert ext.name == "SecurityPolicyExtension"
