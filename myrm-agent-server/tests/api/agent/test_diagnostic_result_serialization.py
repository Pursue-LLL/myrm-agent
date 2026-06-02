"""Test ERROR event diagnostic_result serialization

Verify that ERROR events include diagnostic_result field with correct structure.
"""

import json
import uuid

from fastapi.testclient import TestClient


class TestDiagnosticResultSerialization:
    """Test diagnostic_result in ERROR events"""

    def test_error_event_includes_diagnostic_result(self, client: TestClient) -> None:
        """Verify ERROR event includes diagnostic_result with correct structure"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        # Use invalid model to trigger error
        request_body = {
            "query": "Test query that will fail",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": "invalid-model-xyz-123"},
            "timezone": "Asia/Shanghai",
            "locale": "en",
        }

        print("\n=== Test Diagnostic Result in ERROR Event ===")

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback(providers_dict=None):
            return ModelConfig(model="invalid-model-xyz-123", api_key="sk-123", base_url=None)

        patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback)
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                error_found = False
                diagnostic_result_found = False

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "error":
                            error_found = True
                            print("ERROR event received")

                            diagnostic = data.get("diagnostic_result") or data.get("extra_data", {}).get("diagnostic_result")
                            if diagnostic:
                                diagnostic_result_found = True

                                print("diagnostic_result found:")
                                print(f"  error_type: {diagnostic.get('error_type')}")
                                print(f"  locale: {diagnostic.get('locale')}")
                                print(f"  user_message: {diagnostic.get('user_message', '')[:100]}...")
                                print(f"  resolution_steps count: {len(diagnostic.get('resolution_steps', []))}")

                                # Verify structure
                                assert "error_type" in diagnostic, "diagnostic_result missing error_type"
                                assert "user_message" in diagnostic, "diagnostic_result missing user_message"
                                assert "resolution_steps" in diagnostic, "diagnostic_result missing resolution_steps"
                                assert "locale" in diagnostic, "diagnostic_result missing locale"

                                # Verify types
                                assert isinstance(diagnostic["error_type"], str), "error_type should be str"
                                assert isinstance(diagnostic["user_message"], str), "user_message should be str"
                                assert isinstance(diagnostic["resolution_steps"], list), "resolution_steps should be list"
                                assert isinstance(diagnostic["locale"], str), "locale should be str"

                                # Verify non-empty
                                assert diagnostic["user_message"], "user_message should not be empty"
                                assert diagnostic["locale"], "locale should not be empty"

                            break
                    except json.JSONDecodeError:
                        continue

                assert error_found, "Expected error event but none received"
                assert diagnostic_result_found, "Expected diagnostic_result in error event but not found"
        finally:
            patcher.stop()

    def test_diagnostic_result_respects_locale(self, client: TestClient) -> None:
        """Verify diagnostic_result locale matches request locale"""
        test_cases = [
            ("en", "en"),
            ("zh-CN", "zh-CN"),
            ("ja", "ja"),
            ("ko", "ko"),
            ("de", "de"),
        ]

        for request_locale, expected_locale in test_cases:
            message_id = str(uuid.uuid4())
            chat_id = str(uuid.uuid4())

            request_body = {
                "query": "Test query that will fail",
                "message_id": message_id,
                "chat_id": chat_id,
                "action_mode": "fast",
                "model_selection": {"providerId": "default", "model": f"invalid-model-{request_locale}"},
                "timezone": "Asia/Shanghai",
                "locale": request_locale,
            }

            print(f"\n=== Test Locale: {request_locale} ===")

            from unittest.mock import patch

            from app.core.types import ModelConfig

            def mock_fallback_locale(providers_dict=None, locale=request_locale):
                return ModelConfig(model=f"invalid-model-{locale}", api_key="sk-123", base_url=None)

            patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_locale)
            patcher.start()
            try:
                with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                    for line in response.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        try:
                            data = json.loads(line[6:])
                            diagnostic = data.get("diagnostic_result") or data.get("extra_data", {}).get("diagnostic_result")
                            if data.get("type") == "error" and diagnostic:
                                actual_locale = diagnostic.get("locale")

                                print(f"  Request locale: {request_locale}")
                                print(f"  Diagnostic locale: {actual_locale}")

                                assert actual_locale == expected_locale, (
                                    f"diagnostic_result locale mismatch: expected {expected_locale}, got {actual_locale}"
                                )
                                break
                        except json.JSONDecodeError:
                            continue
            finally:
                patcher.stop()

    def test_diagnostic_result_resolution_steps_not_empty(self, client: TestClient) -> None:
        """Verify diagnostic_result resolution_steps is not empty for known errors"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test query that will fail",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": "invalid-model-abc"},
            "timezone": "Asia/Shanghai",
            "locale": "en",
        }

        print("\n=== Test Resolution Steps ===")

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback_res(providers_dict=None):
            return ModelConfig(model="invalid-model-abc", api_key="sk-123", base_url=None)

        patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_res)
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                resolution_steps_found = False

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        diagnostic = data.get("diagnostic_result") or data.get("extra_data", {}).get("diagnostic_result")
                        if data.get("type") == "error" and diagnostic:
                            resolution_steps = diagnostic.get("resolution_steps", [])

                            print(f"resolution_steps count: {len(resolution_steps)}")
                            if resolution_steps:
                                print("Steps:")
                                for i, step in enumerate(resolution_steps, 1):
                                    print(f"  {i}. {step[:80]}...")

                            # Most errors should have resolution steps
                            # (except 'unknown' type which may have empty steps)
                            if diagnostic.get("error_type") != "unknown":
                                assert len(resolution_steps) > 0, (
                                    f"Expected non-empty resolution_steps for error_type {diagnostic.get('error_type')}"
                                )

                            resolution_steps_found = True
                            break
                    except json.JSONDecodeError:
                        continue

                assert resolution_steps_found, "Did not receive diagnostic_result with resolution_steps"
        finally:
            patcher.stop()
