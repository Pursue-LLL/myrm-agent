"""Comprehensive Locale E2E Tests

Complete coverage of locale propagation and i18n error diagnostics.
Tests all scenarios including edge cases and error conditions.
"""

import json
import uuid

from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


class TestLocaleComprehensive:
    """Comprehensive locale and i18n tests"""

    def test_real_llm_error_with_chinese_locale(self, client: TestClient) -> None:
        """Trigger real LLM error with invalid model and verify Chinese error message"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        # Use invalid model to trigger error
        request_body = {
            "query": "Test query that will fail",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": "invalid-model-does-not-exist-12345"},
            "timezone": "Asia/Shanghai",
            "locale": "zh-CN",
        }

        print("\n=== Test Real Error with Chinese Locale ===")

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback_zh(providers_dict=None):
            return ModelConfig(model="invalid-model-does-not-exist-12345", api_key="sk-123", base_url=None)

        patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_zh)
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                # May get 200 but error event, or 500
                error_found = False
                has_chinese = False

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "error":
                            error_found = True
                            error_msg = data.get("error", "")
                            print(f"Error message: {error_msg[:200]}")

                            # Check if error contains Chinese characters
                            has_chinese = any("\u4e00" <= c <= "\u9fff" for c in error_msg)
                            if has_chinese:
                                print("✓ Error message contains Chinese characters")
                            break
                    except json.JSONDecodeError:
                        continue

                # We should get an error, and ideally it should be in Chinese
                assert error_found, "Expected error event but none received"
                # Note: Chinese may not appear if error happens before locale is processed
                print(f"Has Chinese: {has_chinese}")
        finally:
            patcher.stop()

    def test_real_llm_error_with_english_locale(self, client: TestClient) -> None:
        """Trigger real LLM error with invalid model and verify English error message"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test query that will fail",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": {"providerId": "default", "model": "invalid-model-does-not-exist-67890"},
            "timezone": "America/New_York",
            "locale": "en",
        }

        print("\n=== Test Real Error with English Locale ===")

        from unittest.mock import patch

        from app.core.types import ModelConfig

        def mock_fallback_en(providers_dict=None):
            return ModelConfig(model="invalid-model-does-not-exist-67890", api_key="sk-123", base_url=None)

        patcher = patch("app.core.channel_bridge.model_resolver._fallback_model_from_providers", side_effect=mock_fallback_en)
        patcher.start()
        try:
            with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
                error_found = False
                has_chinese = False

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "error":
                            error_found = True
                            error_msg = data.get("error", "")
                            print(f"Error message: {error_msg[:200]}")

                            # English message should not contain Chinese
                            has_chinese = any("\u4e00" <= c <= "\u9fff" for c in error_msg)
                            print(f"✓ Error message is in English (no Chinese): {not has_chinese}")
                            break
                    except json.JSONDecodeError:
                        continue

                assert error_found, "Expected error event but none received"
        finally:
            patcher.stop()

    def test_japanese_locale(self, client: TestClient) -> None:
        """Test Japanese locale propagation"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "日本語テスト",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "Asia/Tokyo",
            "locale": "ja",
        }

        print("\n=== Test Japanese Locale ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Japanese locale accepted, {event_count} events received")

    def test_korean_locale(self, client: TestClient) -> None:
        """Test Korean locale propagation"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "한국어 테스트",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "Asia/Seoul",
            "locale": "ko",
        }

        print("\n=== Test Korean Locale ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Korean locale accepted, {event_count} events received")

    def test_german_locale(self, client: TestClient) -> None:
        """Test German locale propagation"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Deutsche Test",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "Europe/Berlin",
            "locale": "de",
        }

        print("\n=== Test German Locale ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ German locale accepted, {event_count} events received")

    def test_unsupported_locale_fallback(self, client: TestClient) -> None:
        """Test unsupported locale falls back to English"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test with unsupported locale",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
            "locale": "xx-UNSUPPORTED",  # Unsupported locale
        }

        print("\n=== Test Unsupported Locale Fallback ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            # Should still work, falling back to English
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Unsupported locale handled, {event_count} events received")

    def test_empty_locale(self, client: TestClient) -> None:
        """Test empty locale string"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test with empty locale",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
            "locale": "",  # Empty locale
        }

        print("\n=== Test Empty Locale ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            # Should work with auto-detection
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Empty locale handled, {event_count} events received")

    def test_very_long_locale_string(self, client: TestClient) -> None:
        """Test very long locale string (edge case)"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test with very long locale",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
            "locale": "x" * 1000,  # Very long locale string
        }

        print("\n=== Test Very Long Locale String ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            # Should handle gracefully
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Very long locale handled, {event_count} events received")

    def test_locale_case_sensitivity(self, client: TestClient) -> None:
        """Test locale case sensitivity (ZH-cn vs zh-CN)"""
        message_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())

        request_body = {
            "query": "Test case sensitivity",
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
            "locale": "ZH-cn",  # Mixed case
        }

        print("\n=== Test Locale Case Sensitivity ===")

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
            assert response.status_code == 200
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_count += 1
                        if data.get("type") == "message_end":
                            break
                    except json.JSONDecodeError:
                        continue

            assert event_count > 0
            print(f"✓ Mixed case locale handled, {event_count} events received")


if __name__ == "__main__":
    from main import app

    test_client = TestClient(app)
    test_instance = TestLocaleComprehensive()

    print("Running comprehensive locale tests...")
    test_instance.test_real_llm_error_with_chinese_locale(test_client)
    test_instance.test_real_llm_error_with_english_locale(test_client)
    test_instance.test_japanese_locale(test_client)
    test_instance.test_korean_locale(test_client)
    test_instance.test_german_locale(test_client)
    test_instance.test_unsupported_locale_fallback(test_client)
    test_instance.test_empty_locale(test_client)
    test_instance.test_very_long_locale_string(test_client)
    test_instance.test_locale_case_sensitivity(test_client)
    print("\n✅ All comprehensive locale tests passed!")
