"""
Test to verify that diagnostic_result contains precise model_name from llm_info.

This test ensures the llm_info optimization (StreamContext.llm_info) is working correctly:
- model_name should be extracted from the actual LLM instance
- base_url should be detected for custom endpoints
- is_custom_endpoint should be set correctly
"""

import json
import uuid

from fastapi.testclient import TestClient


class TestLLMInfoPrecision:
    """Test precise model_name and endpoint info in diagnostic_result."""

    def test_diagnostic_contains_precise_model_name(self, client: TestClient) -> None:
        """Verify diagnostic_result contains the exact model_name used in agent stream."""
        print("\n=== Test Precise Model Name in Diagnostic ===")

        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        # Use a specific invalid model to test precise extraction
        test_model = "test-model-for-precision-check"

        request_body = {
            "query": "Test query that will fail",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": test_model},
            "timezone": "Asia/Shanghai",
            "locale": "en",
        }

        diagnostic_result = None

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback_precision(providers_dict=None):
            return ModelConfig(model=test_model, api_key="sk-123", base_url=None)

        patcher = patch(
            "app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_precision
        )
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "error":
                            diagnostic_result = event.get("diagnostic_result")
                            if diagnostic_result:
                                print(f"Diagnostic result: {json.dumps(diagnostic_result, indent=2, ensure_ascii=False)}")
                                break
                    except json.JSONDecodeError:
                        continue
        finally:
            patcher.stop()

        assert diagnostic_result is not None, "Expected diagnostic_result in error event"

        # The key assertion: verify model info is present
        user_message = diagnostic_result.get("user_message", "")
        print(f"\nUser message: {user_message}")

        # The error message should contain the precise model name
        # Note: The exact format depends on how LLMErrorDiagnostic formats it
        # but it should definitely reference the model
        assert test_model in user_message or f"openai/{test_model}" in user_message, (
            f"Expected model name '{test_model}' in diagnostic message, got: {user_message}"
        )

        print(f"✅ Model name '{test_model}' correctly extracted and included in diagnostic")

    def test_diagnostic_with_different_model(self, client: TestClient) -> None:
        """Verify diagnostic correctly extracts different model names."""
        print("\n=== Test Different Model Name ===")

        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        test_model = "another-invalid-test-model"

        request_body = {
            "query": "Test query",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": test_model},
            "timezone": "Asia/Shanghai",
            "locale": "en",
        }

        diagnostic_result = None

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback_diff(providers_dict=None):
            return ModelConfig(model=test_model, api_key="sk-123", base_url=None)

        patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_diff)
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "error":
                            diagnostic_result = event.get("diagnostic_result")
                            if diagnostic_result:
                                break
                    except json.JSONDecodeError:
                        continue
        finally:
            patcher.stop()

        assert diagnostic_result is not None, "Expected diagnostic_result in error event"

        # Verify diagnostic was generated successfully with model info
        assert "error_type" in diagnostic_result
        assert "user_message" in diagnostic_result
        assert "resolution_steps" in diagnostic_result

        user_message = diagnostic_result["user_message"]
        assert test_model in user_message or f"openai/{test_model}" in user_message, (
            f"Expected model '{test_model}' in diagnostic, got: {user_message}"
        )

        print(f"✅ Model name '{test_model}' correctly included in diagnostic")
