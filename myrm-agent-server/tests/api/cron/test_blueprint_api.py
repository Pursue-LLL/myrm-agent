"""Integration test for cron Blueprint REST API endpoints.

Full-path tests: HTTP → router → blueprint registry → response.
No mocking — validates the real blueprint catalog is served correctly.

[POS]
Integration test for cron blueprint API endpoints.
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.api.cron.routes.blueprints import router as blueprint_router
from app.core.cron.blueprint_i18n_supplement import BLUEPRINT_UI_LOCALES
from app.core.cron.blueprints import BUILTIN_BLUEPRINTS

# Blueprints with required empty-default text slots need explicit values in fill tests.
_FILL_VALUE_OVERRIDES: dict[str, dict[str, str]] = {
    "custom_reminder": {"message": "Water the plants"},
    "competitor_watch": {"competitors": "Acme Corp"},
    "social_media_watch": {"brand": "MyBrand"},
}


class FakeDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(blueprint_router, prefix="/cron")
    return TestClient(app)


@pytest.fixture
def full_cron_client() -> Generator[TestClient, None, None]:
    """Client with full cron router for fill→create lifecycle tests."""
    from app.api.cron.routes import helpers, router

    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=FakeDelivery(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)

    app = FastAPI()
    app.include_router(router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=manager):
        yield TestClient(app)


# ---------------------------------------------------------------------------
# GET /cron/blueprints — catalog listing
# ---------------------------------------------------------------------------


class TestListBlueprints:
    """GET /cron/blueprints integration — catalog completeness and ordering."""

    def test_returns_all_registered_blueprints(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == len(BUILTIN_BLUEPRINTS)

    def test_read_it_later_present_in_catalog(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        ids = [bp["id"] for bp in resp.json()]
        assert "read_it_later" in ids

    def test_read_it_later_complete_fields(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        bp = next(b for b in resp.json() if b["id"] == "read_it_later")
        assert bp["icon"] == "BookmarkPlus"
        assert bp["category"] == "productivity"
        assert "en" in bp["title"]
        assert "zh" in bp["title"]
        assert "ja" in bp["title"]
        assert "en" in bp["description"]
        assert "zh" in bp["description"]
        assert "ja" in bp["description"]
        assert "en" in bp["prompt_template"]
        assert "zh" in bp["prompt_template"]
        assert len(bp["slots"]) == 2
        slot_names = {s["name"] for s in bp["slots"]}
        assert slot_names == {"time", "weekdays"}
        assert "read-it-later" in bp["tags"]

    def test_sort_order_monotonically_increasing(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        orders = [bp["sort_order"] for bp in resp.json()]
        assert orders == sorted(orders)

    def test_all_blueprints_have_five_locale_fields(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        for bp in resp.json():
            for locale in BLUEPRINT_UI_LOCALES:
                assert locale in bp["title"], f"{bp['id']} missing {locale} title"
                assert locale in bp["description"], f"{bp['id']} missing {locale} description"
                assert locale in bp["prompt_template"], f"{bp['id']} missing {locale} prompt_template"

    def test_all_blueprints_have_non_empty_slots(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        for bp in resp.json():
            assert len(bp["slots"]) >= 1, f"{bp['id']} has no slots"
            for slot in bp["slots"]:
                assert slot["name"], f"{bp['id']} has empty slot name"
                assert slot["type"] in ("time", "text", "enum")

    def test_unique_ids(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        ids = [bp["id"] for bp in resp.json()]
        assert len(ids) == len(set(ids))

    def test_response_schema_contract(self, client: TestClient) -> None:
        """Every blueprint object adheres to BlueprintResponse schema."""
        resp = client.get("/cron/blueprints")
        required_keys = {"id", "icon", "title", "description", "prompt_template", "slots", "category", "tags", "sort_order"}
        for bp in resp.json():
            assert required_keys.issubset(bp.keys()), f"{bp['id']} missing keys: {required_keys - bp.keys()}"


# ---------------------------------------------------------------------------
# POST /cron/blueprints/fill — prompt + schedule generation
# ---------------------------------------------------------------------------


class TestFillBlueprint:
    """POST /cron/blueprints/fill — slot interpolation and schedule generation."""

    def test_fill_read_it_later_defaults(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schedule"]["kind"] == "cron"
        assert data["schedule"]["expr"] == "0 6 * * *"
        assert "read-it-later" in data["prompt"].lower()
        assert data["name"]
        assert data["required_capabilities"] == ["net_fetch", "file_read"]
        assert data["tools_allowed"] == ["web_fetch", "file_read"]

    def test_fill_news_digest_includes_web_defaults(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "news_digest", "values": {"topic": "AI"}, "locale": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required_capabilities"] == ["web_search_tool", "net_fetch"]
        assert data["tools_allowed"] == ["web_search"]

    def test_fill_financial_simple_returns_router_defaults(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "financial_monitor_simple", "values": {}, "locale": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_type"] == "router"
        assert data["session_target"] == "isolated"
        assert data["deduplicate"] is True
        assert data["skip_if_active"] is True
        assert data["pre_condition_script"] is not None
        assert 'asset_id = "bitcoin"' in data["pre_condition_script"]
        assert data["failure_alert"] == {"enabled": True, "after": 2, "cooldown_seconds": 900}

    def test_fill_financial_advanced_returns_monitor_defaults(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "financial_monitor_advanced", "values": {}, "locale": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_type"] == "agent"
        assert data["session_target"] == "daily"
        assert data["deduplicate"] is True
        assert data["monitor_config"] == {"monitor_type": "hash", "ttl_days": 14, "enabled": True}
        assert data["failure_alert"] == {"enabled": True, "after": 2, "cooldown_seconds": 900}

    def test_fill_financial_simple_invalid_bounds_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "financial_monitor_simple",
                "values": {
                    "lower_bound": "70000",
                    "upper_bound": "60000",
                },
                "locale": "en",
            },
        )
        assert resp.status_code == 422
        assert "lower_bound must be less than upper_bound" in resp.json()["detail"]

    def test_fill_read_it_later_zh_locale(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "zh"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "稍后读" in data["prompt"] or "知识库" in data["prompt"]

    def test_fill_read_it_later_custom_weekends(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "read_it_later",
                "values": {"time": "22:30", "weekdays": "weekends"},
                "locale": "en",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schedule"]["expr"] == "30 22 * * 0,6"

    def test_fill_read_it_later_weekdays_only(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "read_it_later",
                "values": {"time": "07:00", "weekdays": "weekdays"},
                "locale": "en",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["schedule"]["expr"] == "0 7 * * 1-5"

    def test_fill_unknown_blueprint_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "nonexistent_xyz", "values": {}},
        )
        assert resp.status_code == 404
        assert "nonexistent_xyz" in resp.json()["detail"]

    def test_fill_empty_required_slot_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "custom_reminder",
                "values": {"time": "09:00", "message": ""},
                "locale": "en",
            },
        )
        assert resp.status_code == 422
        assert "message" in resp.json()["detail"]

    def test_fill_social_media_watch_empty_keywords_succeeds(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "social_media_watch",
                "values": {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "Myrm",
                    "platforms": "Xiaohongshu, Weibo",
                    "keywords": "",
                },
                "locale": "en",
            },
        )
        assert resp.status_code == 200
        assert "Myrm" in resp.json()["prompt"]

    def test_catalog_exposes_optional_on_keywords_slot(self, client: TestClient) -> None:
        resp = client.get("/cron/blueprints")
        social = next(bp for bp in resp.json() if bp["id"] == "social_media_watch")
        keywords = next(s for s in social["slots"] if s["name"] == "keywords")
        assert keywords["optional"] is True
        brand = next(s for s in social["slots"] if s["name"] == "brand")
        assert brand["optional"] is False

    def test_fill_social_media_empty_brand_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "social_media_watch",
                "values": {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "",
                    "platforms": "Xiaohongshu, Weibo",
                    "keywords": "",
                },
                "locale": "en",
            },
        )
        assert resp.status_code == 422
        assert "brand" in resp.json()["detail"]

    def test_fill_social_media_omitted_keywords_succeeds(self, client: TestClient) -> None:
        """Keywords key omitted entirely — optional slot uses default empty string."""
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "social_media_watch",
                "values": {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "Myrm",
                    "platforms": "Xiaohongshu, Weibo",
                },
                "locale": "en",
            },
        )
        assert resp.status_code == 200
        assert "Myrm" in resp.json()["prompt"]

    def test_fill_social_media_with_keywords_succeeds(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "social_media_watch",
                "values": {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "Myrm",
                    "platforms": "Xiaohongshu, Weibo",
                    "keywords": "AI, product launch",
                },
                "locale": "en",
            },
        )
        assert resp.status_code == 200
        prompt = resp.json()["prompt"]
        assert "AI, product launch" in prompt

    def test_fill_prompt_no_unresolved_placeholders(self, client: TestClient) -> None:
        """read_it_later has no text slots — prompt must not contain Python format braces."""
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "en"},
        )
        prompt = resp.json()["prompt"]
        assert "{" not in prompt
        assert "}" not in prompt

    def test_fill_with_tz_passthrough(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "en", "tz": "Asia/Shanghai"},
        )
        assert resp.status_code == 200
        assert resp.json()["schedule"]["tz"] == "Asia/Shanghai"

    def test_fill_fallback_locale(self, client: TestClient) -> None:
        """Unknown locale falls back to 'en'."""
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "fr"},
        )
        assert resp.status_code == 200
        assert "read-it-later" in resp.json()["prompt"].lower()

    def test_fill_japanese_locale(self, client: TestClient) -> None:
        resp = client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "ja"},
        )
        assert resp.status_code == 200
        assert "後で読む" in resp.json()["prompt"]

    def test_fill_all_blueprints_succeed(self, client: TestClient) -> None:
        """Every registered blueprint can be filled with defaults without error."""
        list_resp = client.get("/cron/blueprints")
        for bp in list_resp.json():
            values = _FILL_VALUE_OVERRIDES.get(bp["id"], {})
            resp = client.post(
                "/cron/blueprints/fill",
                json={"blueprint_id": bp["id"], "values": values, "locale": "en"},
            )
            assert resp.status_code == 200, f"fill failed for {bp['id']}: {resp.text}"
            data = resp.json()
            assert data["schedule"]["kind"] == "cron"
            assert data["prompt"]

    def test_fill_all_blueprints_zh(self, client: TestClient) -> None:
        """Every blueprint produces valid Chinese prompts."""
        list_resp = client.get("/cron/blueprints")
        for bp in list_resp.json():
            values = _FILL_VALUE_OVERRIDES.get(bp["id"], {})
            resp = client.post(
                "/cron/blueprints/fill",
                json={"blueprint_id": bp["id"], "values": values, "locale": "zh"},
            )
            assert resp.status_code == 200, f"fill zh failed for {bp['id']}: {resp.text}"


# ---------------------------------------------------------------------------
# Fill → Create lifecycle (Blueprint-driven cron job creation)
# ---------------------------------------------------------------------------


class TestBlueprintToCronLifecycle:
    """Integration: fill blueprint → create cron job from result."""

    def test_fill_then_create_cron_job(self, full_cron_client: TestClient) -> None:
        """Simulate frontend: fill blueprint → use result to create cron job."""
        fill_resp = full_cron_client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {"time": "06:00"}, "locale": "en"},
        )
        assert fill_resp.status_code == 200
        fill_data = fill_resp.json()

        create_resp = full_cron_client.post(
            "/cron",
            json={
                "name": fill_data["name"],
                "job_type": "agent",
                "schedule": fill_data["schedule"],
                "prompt": fill_data["prompt"],
            },
        )
        assert create_resp.status_code == 201
        job = create_resp.json()
        assert job["status"] == "active"
        assert job["prompt"] == fill_data["prompt"]

    def test_social_media_empty_keywords_lifecycle(self, full_cron_client: TestClient) -> None:
        """Brand-only social watch: empty optional keywords → fill → create job."""
        fill_resp = full_cron_client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "social_media_watch",
                "values": {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "E2EBrand",
                    "platforms": "Xiaohongshu, Weibo",
                    "keywords": "",
                },
                "locale": "zh",
            },
        )
        assert fill_resp.status_code == 200, fill_resp.text
        fill_data = fill_resp.json()
        assert "E2EBrand" in fill_data["prompt"]

        create_resp = full_cron_client.post(
            "/cron",
            json={
                "name": fill_data["name"],
                "job_type": "agent",
                "schedule": fill_data["schedule"],
                "prompt": fill_data["prompt"],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        job = create_resp.json()
        assert job["status"] == "active"
        assert "E2EBrand" in job["prompt"]

    def test_fill_then_create_with_weekdays(self, full_cron_client: TestClient) -> None:
        fill_resp = full_cron_client.post(
            "/cron/blueprints/fill",
            json={
                "blueprint_id": "read_it_later",
                "values": {"time": "20:00", "weekdays": "weekdays"},
                "locale": "zh",
            },
        )
        assert fill_resp.status_code == 200
        fill_data = fill_resp.json()

        create_resp = full_cron_client.post(
            "/cron",
            json={
                "name": fill_data["name"],
                "job_type": "agent",
                "schedule": fill_data["schedule"],
                "prompt": fill_data["prompt"],
            },
        )
        assert create_resp.status_code == 201
        job = create_resp.json()
        assert "1-5" in job["schedule"]["expr"]

    def test_created_job_is_retrievable(self, full_cron_client: TestClient) -> None:
        """Created job can be fetched back via GET."""
        fill_resp = full_cron_client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {}, "locale": "en"},
        )
        fill_data = fill_resp.json()

        create_resp = full_cron_client.post(
            "/cron",
            json={
                "name": fill_data["name"],
                "job_type": "agent",
                "schedule": fill_data["schedule"],
                "prompt": fill_data["prompt"],
            },
        )
        job_id = create_resp.json()["id"]

        get_resp = full_cron_client.get(f"/cron/{job_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["prompt"] == fill_data["prompt"]


# ---------------------------------------------------------------------------
# Prebuilt skill sync — read-it-later SKILL.md discovery
# ---------------------------------------------------------------------------


class TestPrebuiltSkillDiscovery:
    """Validates that the read-it-later SKILL.md is discoverable by prebuilt_sync."""

    def test_skill_dir_exists(self) -> None:
        from app.core.skills.prebuilt_sync import SEEDS_DIR

        skill_dir = SEEDS_DIR / "read-it-later"
        assert skill_dir.is_dir()

    def test_skill_md_parseable(self) -> None:
        from myrm_agent_harness.api.skills import parse_skill_frontmatter

        from app.core.skills.prebuilt_sync import SEEDS_DIR

        skill_md = SEEDS_DIR / "read-it-later" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        fm = parse_skill_frontmatter(content, "read-it-later")
        assert fm.name == "read-it-later"
        assert fm.description
        assert fm.category == "productivity"
        assert fm.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_sync_prebuilt_seeds_discovers_read_it_later(self, tmp_path: object) -> None:
        import tempfile

        from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

        import app.core.skills.prebuilt_sync as sync_mod
        from app.core.skills.prebuilt_sync import sync_prebuilt_seeds

        with tempfile.TemporaryDirectory() as tmpdir:
            sync_mod._synced = False
            try:
                storage = LocalStorageBackend(tmpdir)
                result = await sync_prebuilt_seeds(storage)
                assert "read-it-later" in result.skill_ids
                assert result.synced_count >= 1
            finally:
                sync_mod._synced = True
