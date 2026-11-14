"""In-memory credential store for the skill availability tests: the rows a verdict and a turn both read.

``credentials`` is a fixture over a real ORM database (``UserConfig`` and its audit table) that the config service,
the OAuth store and ``app.database.connection.get_session`` all read, so the production gate, the production loaders
and the production assembler run unmodified. A test stores the credential state it needs through ``CredentialStore``
instead of stubbing a private predicate of the gate. A test that already owns a database with the full schema (the
skills API tests) binds the same readers to it through ``bind_credential_readers``.

``prebuilt_skill_metadata`` / ``prebuilt_catalog_skill`` give the skills as shipped (``assets/prebuilt_skills``),
parsed by the harness parser the loaders use, so a test exercises the frontmatter the product really declares.

Registered globally through ``pytest_plugins`` in ``tests/conftest.py``. It is a plugin module, not a conftest: a
conftest that is also a plugin is registered twice, and pytest then aborts any run that targets its directory.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator, AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from myrm_agent_harness.api.skills import build_skill_metadata, parse_skill_frontmatter
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillTrust
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.channel_bridge import config_cache
from app.core.skills.models import Skill
from app.core.storage.types import SkillType
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService
from app.services.integrations.oauth_store import upsert_oauth_credential

PREBUILT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills"

XAI_API_URL = "https://api.x.ai/v1"
XaiProviderRow = Literal["key", "no-key"]

_PROVIDERS_CONFIG_KEY = "providers"
_DEFAULT_MODEL = {"baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o"}}}
_OPENAI_ROW: dict[str, object] = {
    "id": "openai",
    "name": "openai",
    "isEnabled": True,
    "apiUrl": "https://api.openai.com/v1",
    "providerType": "openai",
    "apiKeys": [{"id": "key-openai", "key": "sk-test-openai", "remark": "", "isActive": True}],
}
_XAI_ROW: dict[str, object] = {
    "id": "xai",
    "name": "xai",
    "isEnabled": True,
    "apiUrl": XAI_API_URL,
    "apiKeys": [{"id": "key-xai", "key": "xai-test-key", "remark": "", "isActive": True}],
}
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class CredentialState:
    """What one install has stored: an xAI provider row (with or without a key), a SuperGrok token, a Google token."""

    xai_provider: XaiProviderRow | None = None
    supergrok: bool = False
    google: bool = False


class CredentialStore:
    """Writes the rows the Settings pages write: the provider bundle and the OAuth credential blob."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def store_providers(self, rows: Sequence[Mapping[str, object]], *, default_model: bool = True) -> None:
        """Store the provider bundle encrypted, as the config service does; ``default_model=False`` is a fresh install."""
        bundle: dict[str, object] = {"providers": [dict(row) for row in rows]}
        if default_model:
            bundle["defaultModelConfig"] = _DEFAULT_MODEL
        stored, encrypted = service._encrypt_if_sensitive(_PROVIDERS_CONFIG_KEY, bundle)  # noqa: SLF001
        async with self.sessions() as db:
            db.add(
                UserConfig(
                    id="id-providers",
                    config_key=_PROVIDERS_CONFIG_KEY,
                    config_value={"_cipher": stored} if encrypted else bundle,
                    is_encrypted=encrypted,
                    version="1_0",
                    last_device_id="test",
                    updated_at=datetime.now(UTC),
                )
            )
            await db.commit()

    async def store_oauth(self, entries: Mapping[str, Mapping[str, object]]) -> None:
        """Store OAuth entries keyed by issuer, through the writer behind the Credentials page."""
        async with self.sessions() as db:
            for issuer, entry in entries.items():
                await upsert_oauth_credential(db, issuer, dict(entry))

    async def seed(self, state: CredentialState, *, default_model: bool = True) -> None:
        """Store one credential state; the SuperGrok token is far from expiry, so no load refreshes it over the network."""
        rows: list[Mapping[str, object]] = [_OPENAI_ROW]
        if state.xai_provider == "key":
            rows.append(_XAI_ROW)
        elif state.xai_provider == "no-key":
            rows.append({**_XAI_ROW, "apiKeys": []})
        await self.store_providers(rows, default_model=default_model)

        oauth: dict[str, Mapping[str, object]] = {}
        if state.supergrok:
            oauth["xai"] = {
                "token": "supergrok-token",
                "base_url": XAI_API_URL,
                "expires_at": time.time() + 30 * _SECONDS_PER_DAY,
            }
        if state.google:
            oauth["google_workspace"] = {"token": "google-token", "scope": "https://www.googleapis.com/auth/drive.readonly"}
        await self.store_oauth(oauth)


def bind_credential_readers(monkeypatch: pytest.MonkeyPatch, sessions: async_sessionmaker[AsyncSession]) -> CredentialStore:
    """Point every reader and writer of stored credentials at ``sessions`` (one with the ``UserConfig`` table).

    Binds before anything is stored through the returned store: the rows are encrypted with a key made for this call.
    The loader's config cache is private to the test: the stored rows are not served to a test that runs after it, and
    the entry an earlier test left cached is neither served here nor dropped.
    """

    @asynccontextmanager
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    encryption = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr("app.database.connection.get_session", get_session)
    monkeypatch.setattr(service, "get_session_factory", lambda: sessions)
    monkeypatch.setattr(service, "get_encryption_service", lambda: encryption)
    monkeypatch.setattr("app.services.config.encryption.get_encryption_service", lambda: encryption)
    monkeypatch.setattr("app.services.integrations.oauth_store.get_encryption_service", lambda: encryption)
    monkeypatch.setattr(config_cache, "_config_cache", {})
    config_cache.invalidate_user_configs_cache()
    return CredentialStore(sessions)


@asynccontextmanager
async def credential_store(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[CredentialStore]:
    """An empty in-memory install: every reader of stored credentials is bound to it for the length of the block."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(UserConfig.__table__.create)
        await connection.run_sync(ConfigAuditLog.__table__.create)
    try:
        yield bind_credential_readers(monkeypatch, async_sessionmaker(engine, expire_on_commit=False))
    finally:
        config_cache.invalidate_user_configs_cache()
        await engine.dispose()


@pytest.fixture
async def credentials(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[CredentialStore]:
    async with credential_store(monkeypatch) as store:
        yield store


def prebuilt_skill_metadata(name: str) -> SkillMetadata:
    """The shipped prebuilt skill as the runtime loaders build it from its SKILL.md."""
    content = (PREBUILT_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    return build_skill_metadata(
        skill_name=name,
        frontmatter=parse_skill_frontmatter(content, name),
        storage_path=f"skills/prebuilt/{name}",
        content=content,
        trust=SkillTrust.TRUSTED,
    )


def prebuilt_catalog_skill(name: str) -> Skill:
    """The shipped prebuilt skill as the Skills catalog lists it."""
    return Skill.from_metadata(prebuilt_skill_metadata(name), skill_id=name, skill_type=SkillType.PREBUILT)


def issuer_declaring_prebuilt_skills() -> dict[str, tuple[str, ...]]:
    """Every shipped prebuilt skill that declares OAuth issuers, with the issuers it declares (frontmatter order)."""
    declared: dict[str, tuple[str, ...]] = {}
    for skill_md in sorted(PREBUILT_SKILLS_DIR.glob("*/SKILL.md")):
        name = skill_md.parent.name
        issuers = parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"), name).required_oauth_issuers
        if issuers:
            declared[name] = tuple(issuers)
    return declared
