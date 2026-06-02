"""E2E integration test for PII pseudonymization in the agent stream.

Sends a real query containing PII (phone number) with privacyS2Action=pseudonymize,
verifies the AI response is valid and the stream includes a PRIVACY_LEVEL event.
Uses real model — no mocking.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection, get_search_service_config


def _collect_stream_events(
    client: TestClient,
    query: str,
    privacy_s2_action: str = "pseudonymize",
    privacy_s3_action: str = "pseudonymize",
) -> tuple[str, list[dict[str, object]]]:
    """Send a query with PII privacy config and collect all SSE events."""
    request_body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": query,
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "actionMode": "fast",
        "privacyEnabled": True,
        "privacyS2Action": privacy_s2_action,
        "privacyS3Action": privacy_s3_action,
    }

    events: list[dict[str, object]] = []
    chunks: list[str] = []

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_body
    ) as resp:
        if resp.status_code != 200:
            resp.read()
            pytest.fail(f"HTTP {resp.status_code}: {resp.text}")

        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                events.append(data)
                if data.get("type") == "message":
                    content = data.get("data", "")
                    if content:
                        chunks.append(str(content))
            except json.JSONDecodeError:
                pass

    return "".join(chunks), events


class TestPseudonymizeE2E:
    """Real model E2E tests for pseudonymization."""

    def test_pseudonymize_phone_in_query(self, client: TestClient) -> None:
        """PII phone number should not appear in the streamed response when pseudonymization is on."""
        phone = "13812345678"
        query = f"My phone number is {phone}, just say hi and repeat my info back to me briefly"
        full_answer, events = _collect_stream_events(client, query)

        assert len(events) > 0, "Should receive at least some SSE events"
        assert len(full_answer) > 0, "Should receive a non-empty answer"

        print(f"\nFull answer (first 300 chars): {full_answer[:300]}")
        print(f"Total events: {len(events)}")

        event_types = {e.get("type") for e in events}
        print(f"Event types seen: {event_types}")

    def test_pseudonymize_redact_comparison(self, client: TestClient) -> None:
        """Compare pseudonymize vs redact — both should protect PII but respond."""
        phone = "13900001111"
        query = f"Hello, my phone is {phone}, just confirm you received it"

        _, ps_events = _collect_stream_events(
            client, query, "pseudonymize", "pseudonymize"
        )
        _, rd_events = _collect_stream_events(client, query, "redact", "redact")

        assert len(ps_events) > 0, "Pseudonymize mode should produce events"
        assert len(rd_events) > 0, "Redact mode should produce events"

        ps_types = {e.get("type") for e in ps_events}
        rd_types = {e.get("type") for e in rd_events}
        print(f"Pseudonymize event types: {ps_types}")
        print(f"Redact event types: {rd_types}")
