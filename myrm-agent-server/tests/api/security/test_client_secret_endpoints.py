"""Integration tests for Client Secret Leak Scanning and BFF Refactor API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.client_secret_router import router as client_secret_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting client_secret_router."""
    test_app = FastAPI(title="Client Secret Security Test App")
    test_app.include_router(client_secret_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_scan_client_code_endpoint_leak_and_clean(client: TestClient) -> None:
    """Validate POST /security/client-secrets/scan detects leaks and passes clean code."""
    # 1. Leaked React component
    leaked_payload = {
        "file_path": "src/components/PaymentModal.tsx",
        "code": """
export function PaymentModal() {
  const stripeKey = "sk_live_123456789012345678901234";
  return <div>Stripe Checkout</div>;
}
""",
    }
    resp = client.post("/api/v1/security/client-secrets/scan", json=leaked_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["file_path"] == "src/components/PaymentModal.tsx"
    assert data["is_client_code"] is True
    assert data["has_leak"] is True
    assert data["findings_count"] == 1
    assert data["findings"][0]["secret_type"] == "Stripe Secret Key"
    assert data["findings"][0]["suggested_env_var"] == "STRIPE_SECRET_KEY"

    # 2. Clean component
    clean_payload = {
        "file_path": "src/components/Button.tsx",
        "code": "export function Button() { return <button>Click</button>; }",
    }
    clean_resp = client.post("/api/v1/security/client-secrets/scan", json=clean_payload)
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()

    assert clean_data["has_leak"] is False
    assert clean_data["findings_count"] == 0
    assert len(clean_data["findings"]) == 0


def test_refactor_to_bff_endpoint(client: TestClient) -> None:
    """Validate POST /security/client-secrets/refactor-bff outputs complete BFF remediation."""
    payload = {
        "file_path": "src/app/chat/page.tsx",
        "code": """
import React from 'react';

export default function ChatPage() {
  const apiKey = "sk-proj-9988776655443322110011223344556677889900";
  
  async function request() {
    await fetch("https://api.openai.com/v1/chat/completions", {
      headers: { "Authorization": `Bearer ${apiKey}` },
    });
  }
  return <div>Chat</div>;
}
""",
    }
    resp = client.post("/api/v1/security/client-secrets/refactor-bff", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["original_file_path"] == "src/app/chat/page.tsx"
    assert "/api/proxy" in data["refactored_client_code"]
    assert "https://api.openai.com/v1/chat/completions" not in data["refactored_client_code"]
    assert "OPENAI_API_KEY" in data["extracted_env_entries"]
    assert "src/app/api/proxy/route.ts" in data["server_proxy_file_path"]
    assert "NextResponse" in data["server_proxy_code"]
    assert "process.env.OPENAI_API_KEY" in data["server_proxy_code"]
