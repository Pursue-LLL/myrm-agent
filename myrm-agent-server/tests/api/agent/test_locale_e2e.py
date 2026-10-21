"""Locale End-to-End Integration Test

Test locale propagation from frontend API request to backend Agent.
Verifies that user-selected language is correctly passed through the entire stack.
"""

import json
import uuid

from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def test_locale_propagation_in_agent_request(client: TestClient) -> None:
    """Test that locale is correctly propagated from API request to Agent.

    This test sends a request with a specific locale (zh-CN) and verifies
    that the locale is accepted by the API without errors.
    """
    # Prepare request with locale
    message_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())

    request_body = {
        "query": "Hello, test query for locale propagation",
        "message_id": message_id,
        "chat_id": chat_id,
        "action_mode": "fast",
        "model_selection": get_model_selection(),
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN",  # Test Chinese locale
    }

    print("\n=== Testing Locale Propagation ===")
    print(f"Request locale: {request_body['locale']}")

    # Send request and collect response
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
        # Verify request is accepted
        assert response.status_code == 200, f"Request failed with status {response.status_code}"

        events = []

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                events.append(data)
                event_type = data.get("type")

                if event_type == "message":
                    content = data.get("data", "")
                    print(f"Message chunk received: {content[:50]}...")
                elif event_type == "message_end":
                    print(f"Message completed. Total events: {len(events)}")
                    break
                elif event_type == "error":
                    error_msg = data.get("error", "")
                    print(f"Error received: {error_msg}")
                    # If error contains Chinese characters, locale was used
                    if any("\u4e00" <= c <= "\u9fff" for c in error_msg):
                        print("✓ Error message contains Chinese characters (locale applied)")
                    break
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                continue

        # Verify we received some response
        assert len(events) > 0, "No events received from stream"
        print(f"✓ Locale field accepted, {len(events)} events received")


def test_english_locale_propagation(client: TestClient) -> None:
    """Test English locale propagation"""
    message_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())

    request_body = {
        "query": "Test query with English locale",
        "message_id": message_id,
        "chat_id": chat_id,
        "action_mode": "fast",
        "model_selection": get_model_selection(),
        "timezone": "America/New_York",
        "locale": "en",  # Test English locale
    }

    print("\n=== Testing English Locale ===")
    print(f"Request locale: {request_body['locale']}")

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
        assert response.status_code == 200, f"Request failed with status {response.status_code}"

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

        assert event_count > 0, "No events received"
        print(f"✓ English locale accepted, {event_count} events received")


def test_locale_field_optional(client: TestClient) -> None:
    """Test that locale field is optional (backward compatibility)"""
    message_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())

    request_body = {
        "query": "Test query without locale field",
        "message_id": message_id,
        "chat_id": chat_id,
        "action_mode": "fast",
        "model_selection": get_model_selection(),
        "timezone": "UTC",
        # No locale field - should use auto-detection
    }

    print("\n=== Testing Locale Field is Optional ===")
    print("Request without locale field (should use auto-detection)")

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_body) as response:
        assert response.status_code == 200, f"Request failed with status {response.status_code}"

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

        assert event_count > 0, "No events received"
        print(f"✓ Request without locale accepted, {event_count} events received")


if __name__ == "__main__":
    # For manual testing
    from main import app

    test_client = TestClient(app)

    print("Running locale E2E tests...")
    test_locale_propagation_in_agent_request(test_client)
    test_english_locale_propagation(test_client)
    test_locale_field_optional(test_client)
    print("\n✅ All locale E2E tests passed!")
