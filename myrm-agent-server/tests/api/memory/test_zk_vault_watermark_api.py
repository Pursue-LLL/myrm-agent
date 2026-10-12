"""Unit tests for Zero Knowledge Memory Vault and Provenance Watermarking API (Item 159).

[INPUT]
- FastAPI TestClient, passphrase payloads, memory seal requests, export requirements.

[OUTPUT]
- Asserts verifying /zk-vault/seal, /unseal, /memories, /export, /verify-watermark, /verify-residency endpoints.

[POS]
- Server-side test suite in myrm-agent-server/tests/api/memory/test_zk_vault_watermark_api.py.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.zk_vault_watermark_router import (
    router as zk_vault_watermark_router,
)

app = FastAPI()
app.include_router(zk_vault_watermark_router)
client = TestClient(app)


def test_seal_and_unseal_memory_api() -> None:
    passphrase = "master_vault_passphrase_001"
    seal_payload = {
        "memory_id": "sec_mem_01",
        "content": "Secret API key for internal enterprise gateway: token_998877",
        "sensitivity_tier": "team_internal",
        "category": "credentials",
        "passphrase": passphrase,
    }

    # 1. Seal memory
    seal_resp = client.post("/zk-vault/seal", json=seal_payload)
    assert seal_resp.status_code == 201
    env = seal_resp.json()
    assert env["ciphertext_hex"] != ""
    assert env["salt_hex"] != ""
    assert env["encrypted_dek_hex"] != ""

    # 2. Unseal memory with correct passphrase
    unseal_resp = client.post(
        "/zk-vault/unseal",
        json={"memory_id": "sec_mem_01", "passphrase": passphrase},
    )
    assert unseal_resp.status_code == 200
    item = unseal_resp.json()
    assert item["memory_id"] == "sec_mem_01"
    assert "Secret API key" in item["content"]

    # 3. Unseal with wrong passphrase -> 400 Bad Request
    wrong_resp = client.post(
        "/zk-vault/unseal",
        json={"memory_id": "sec_mem_01", "passphrase": "wrong_passphrase"},
    )
    assert wrong_resp.status_code == 400
    assert "Decryption failed" in wrong_resp.json()["detail"]


def test_list_memories_api() -> None:
    passphrase = "pwd_list_002"
    client.post(
        "/zk-vault/seal",
        json={
            "memory_id": "pub_mem_02",
            "content": "Use TypeScript ESLint rules",
            "sensitivity_tier": "public_sharable",
            "category": "style",
            "passphrase": passphrase,
        },
    )

    list_resp = client.get("/zk-vault/memories", params={"tier": "public_sharable"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(it["memory_id"] == "pub_mem_02" for it in items)


def test_export_distilled_package_and_verify_watermark_api() -> None:
    passphrase = "pwd_export_003"
    client.post(
        "/zk-vault/seal",
        json={
            "memory_id": "exp_mem_03",
            "content": "Contact lead at admin@example.com with key: secret_12345678",
            "sensitivity_tier": "team_internal",
            "category": "workflow",
            "passphrase": passphrase,
        },
    )

    # 1. Export package
    export_payload = {
        "tenant_id": "tenant_phoenix_01",
        "user_id": "user_operator_02",
        "target_tier": "team_internal",
        "redact_pii": True,
        "timestamp_iso": "2026-10-10T12:00:00Z",
    }
    exp_resp = client.post("/zk-vault/export", json=export_payload)
    assert exp_resp.status_code == 200
    pkg = exp_resp.json()
    assert pkg["tenant_id"] == "tenant_phoenix_01"
    assert pkg["watermark_signature"] != ""
    assert "[REDACTED_EMAIL]" in pkg["watermarked_text"]
    assert "[REDACTED_SECRET]" in pkg["watermarked_text"]

    # 2. Verify watermark
    verify_resp = client.post(
        "/zk-vault/verify-watermark",
        json={"exported_text": pkg["watermarked_text"]},
    )
    assert verify_resp.status_code == 200
    wm = verify_resp.json()
    assert wm["tenant_id"] == "tenant_phoenix_01"
    assert wm["user_id"] == "user_operator_02"
    assert wm["signature"] == pkg["watermark_signature"]


def test_verify_residency_and_anti_cloning_api() -> None:
    # 1. Initial binding established
    res1 = client.post(
        "/zk-vault/verify-residency",
        json={
            "instance_guid": "inst_cluster_node_01",
            "volume_id": "vol_nvme_99",
            "tenant_id": "tenant_omega",
        },
    )
    assert res1.status_code == 200
    assert res1.json()["allowed"] is True

    # 2. Same environment passes
    res2 = client.post(
        "/zk-vault/verify-residency",
        json={
            "instance_guid": "inst_cluster_node_01",
            "volume_id": "vol_nvme_99",
            "tenant_id": "tenant_omega",
        },
    )
    assert res2.status_code == 200
    assert res2.json()["allowed"] is True

    # 3. Foreign instance detected -> Alert and locked
    res3 = client.post(
        "/zk-vault/verify-residency",
        json={
            "instance_guid": "inst_foreign_rogue_02",
            "volume_id": "vol_nvme_99",
            "tenant_id": "tenant_omega",
        },
    )
    assert res3.status_code == 200
    assert res3.json()["allowed"] is False
    assert "CRITICAL SECURITY ALERT" in res3.json()["diagnostic"]


def test_unlock_residency_api() -> None:
    unlock_payload = {
        "provided_passphrase": "admin_unlock_token",
        "expected_passphrase": "admin_unlock_token",
        "new_instance_guid": "inst_migrated_node_03",
        "new_volume_id": "vol_nvme_99",
        "tenant_id": "tenant_omega",
    }
    unlock_resp = client.post("/zk-vault/unlock-residency", json=unlock_payload)
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["unlocked"] is True

    # Rebound instance passes
    verify_resp = client.post(
        "/zk-vault/verify-residency",
        json={
            "instance_guid": "inst_migrated_node_03",
            "volume_id": "vol_nvme_99",
            "tenant_id": "tenant_omega",
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["allowed"] is True
