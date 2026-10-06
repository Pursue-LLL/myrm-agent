"""
[POS] tests/api/memory/test_code_memory_compaction_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.code_memory_compaction_router
[OUTPUT] test_compact_code_memory_api, test_extract_single_code_skeleton_api, test_compact_under_tight_budget_api
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.code_memory_compaction_router import (
    router as code_memory_compaction_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting code memory compaction router."""
    test_app = FastAPI()
    test_app.include_router(code_memory_compaction_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_compact_code_memory_api(client: TestClient) -> None:
    """Verify POST /api/memory/compaction/code/compact endpoint with multi-file input."""
    payload = {
        "items": [
            {
                "file_path": "services/auth.py",
                "source_code": """
class AuthService:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def verify_token(self, token: str) -> bool:
        if not token:
            return False
        return len(token) > 10
""",
                "relevance_score": 0.95,
                "language": "python",
            },
            {
                "file_path": "utils/crypto.py",
                "source_code": """
def hash_sha256(text: str) -> str:
    \"\"\"Compute SHA-256 digest.\"\"\"
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()

def generate_salt(rounds: int = 12) -> bytes:
    import os
    return os.urandom(rounds)
""",
                "relevance_score": 0.4,
                "language": "python",
            },
        ],
        "token_budget": 80,
        "strip_private_symbols": False,
        "tokens_per_char_ratio": 0.26,
    }

    resp = client.post("/api/memory/compaction/code/compact", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["budget_limit"] == 80
    assert data["total_compacted_tokens"] <= 80
    assert data["total_original_tokens"] > data["total_compacted_tokens"]
    assert len(data["compacted_blocks"]) == 2

    auth_block = next(b for b in data["compacted_blocks"] if b["file_path"] == "services/auth.py")
    crypto_block = next(b for b in data["compacted_blocks"] if b["file_path"] == "utils/crypto.py")

    assert "class AuthService" in auth_block["content"]
    assert "hash_sha256" in crypto_block["content"]


def test_extract_single_code_skeleton_api(client: TestClient) -> None:
    """Verify POST /api/memory/compaction/code/skeleton endpoint for L1 signatures."""
    payload = {
        "source_code": """
class CacheManager:
    \"\"\"Thread-safe memory cache manager.\"\"\"
    def __init__(self, max_size: int = 500) -> None:
        self.max_size = max_size
        self._entries: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        val = self._entries.get(key)
        return val
""",
        "level": "L1_SIGNATURES",
        "strip_private_symbols": False,
        "language": "python",
    }

    resp = client.post("/api/memory/compaction/code/skeleton", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["abstraction_level"] == "L1_SIGNATURES"
    assert "class CacheManager" in data["content"]
    assert "def get(self, key: str) -> str | None:" in data["content"]
    assert "val = self._entries.get(key)" not in data["content"]
    assert data["compacted_token_count"] < data["original_token_count"]


def test_compact_under_tight_budget_api(client: TestClient) -> None:
    """Verify compaction successfully clamps tokens when given an extremely constrained budget."""
    payload = {
        "items": [
            {
                "file_path": "big_module.py",
                "source_code": "\n".join([f"def func_{i}(x: int) -> int:\n    return x * {i}" for i in range(50)]),
                "relevance_score": 0.8,
                "language": "python",
            }
        ],
        "token_budget": 40,
        "tokens_per_char_ratio": 0.26,
    }

    resp = client.post("/api/memory/compaction/code/compact", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_compacted_tokens"] <= 40
    assert data["compression_ratio"] > 0.8
