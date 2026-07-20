"""Unit tests for cron blueprints — verifies registry integrity and fill logic.

[POS]
Tests for the cron blueprint registry and fill_blueprint function.
"""

from __future__ import annotations

import pytest

from app.core.cron.blueprint_i18n_supplement import BLUEPRINT_UI_LOCALES, SUPPLEMENTAL_BY_ID
from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintFillError,
    fill_blueprint,
    get_blueprint,
    get_blueprints_for_tool_description,
)


class TestBlueprintRegistry:
    """Validate the BUILTIN_BLUEPRINTS registry integrity."""

    def test_all_blueprints_have_unique_ids(self) -> None:
        ids = [bp.id for bp in BUILTIN_BLUEPRINTS]
        assert len(ids) == len(set(ids)), f"Duplicate blueprint IDs: {ids}"

    def test_all_blueprints_have_unique_sort_orders(self) -> None:
        orders = [bp.sort_order for bp in BUILTIN_BLUEPRINTS]
        assert len(orders) == len(set(orders)), f"Duplicate sort_orders: {orders}"

    def test_all_blueprints_have_five_locale_titles(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            for locale in BLUEPRINT_UI_LOCALES:
                assert locale in bp.title, f"{bp.id} missing {locale} title"
                assert bp.title[locale].strip(), f"{bp.id} empty {locale} title"

    def test_all_blueprints_have_five_locale_descriptions(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            for locale in BLUEPRINT_UI_LOCALES:
                assert locale in bp.description, f"{bp.id} missing {locale} description"
                assert bp.description[locale].strip(), f"{bp.id} empty {locale} description"

    def test_all_blueprints_have_five_locale_prompts(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            for locale in BLUEPRINT_UI_LOCALES:
                assert locale in bp.prompt_template, f"{bp.id} missing {locale} prompt"
                assert bp.prompt_template[locale].strip(), f"{bp.id} empty {locale} prompt"

    def test_supplemental_covers_all_builtin_ids(self) -> None:
        builtin_ids = {bp.id for bp in BUILTIN_BLUEPRINTS}
        assert set(SUPPLEMENTAL_BY_ID) == builtin_ids

    def test_all_slot_defaults_are_strings(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            for slot in bp.slots:
                assert isinstance(slot.default, str), (
                    f"{bp.id}.{slot.name} default is not str: {type(slot.default)}"
                )

    def test_prompt_templates_do_not_use_python_format_braces_outside_slots(self) -> None:
        """Ensure no stray {xxx} in prompts that would fail .format()."""
        for bp in BUILTIN_BLUEPRINTS:
            slot_names = {s.name for s in bp.slots}
            for lang, template in bp.prompt_template.items():
                import re

                placeholders = set(re.findall(r"\{(\w+)\}", template))
                stray = placeholders - slot_names
                assert not stray, (
                    f"{bp.id} [{lang}] has unresolved placeholders: {stray}"
                )


class TestReadItLaterBlueprint:
    """Specific tests for the read_it_later blueprint."""

    def test_exists_in_registry(self) -> None:
        bp = get_blueprint("read_it_later")
        assert bp is not None
        assert bp.id == "read_it_later"

    def test_category_is_productivity(self) -> None:
        bp = get_blueprint("read_it_later")
        assert bp is not None
        assert bp.category == "productivity"

    def test_has_time_and_weekdays_slots(self) -> None:
        bp = get_blueprint("read_it_later")
        assert bp is not None
        slot_names = [s.name for s in bp.slots]
        assert "time" in slot_names
        assert "weekdays" in slot_names

    def test_default_time_is_0600(self) -> None:
        bp = get_blueprint("read_it_later")
        assert bp is not None
        time_slot = next(s for s in bp.slots if s.name == "time")
        assert time_slot.default == "06:00"

    def test_fill_produces_valid_cron_expression(self) -> None:
        result = fill_blueprint("read_it_later", {"time": "06:00", "weekdays": "everyday"})
        assert result is not None
        assert result.schedule.kind == "cron"
        assert result.schedule.expr == "0 6 * * *"

    def test_fill_weekdays_only(self) -> None:
        result = fill_blueprint("read_it_later", {"time": "07:30", "weekdays": "weekdays"})
        assert result is not None
        assert result.schedule.expr == "30 7 * * 1-5"

    def test_fill_prompt_does_not_contain_raw_braces(self) -> None:
        result = fill_blueprint("read_it_later", {"time": "06:00", "weekdays": "everyday"})
        assert result is not None
        assert "{" not in result.prompt
        assert "}" not in result.prompt


class TestFinancialMonitorBlueprints:
    """Specific tests for financial monitor simple/advanced blueprints."""

    def test_simple_blueprint_router_defaults_and_script(self) -> None:
        result = fill_blueprint(
            "financial_monitor_simple",
            {
                "time": "08:00",
                "weekdays": "weekdays",
                "asset": "bitcoin",
                "quote_currency": "usd",
                "lower_bound": "50000",
                "upper_bound": "70000",
                "source": "coingecko",
            },
        )
        assert result is not None
        assert result.job_type == "router"
        assert result.session_target == "isolated"
        assert result.pre_condition_script is not None
        assert 'asset_id = "bitcoin"' in result.pre_condition_script
        assert 'lower_bound = float("50000")' in result.pre_condition_script
        assert 'upper_bound = float("70000")' in result.pre_condition_script
        assert "_fetch_from_coingecko" in result.pre_condition_script
        assert "_fetch_from_binance" in result.pre_condition_script
        assert "all_sources_failed" in result.pre_condition_script
        assert result.failure_alert is not None
        assert result.failure_alert.after == 2
        assert result.failure_alert.cooldown_seconds == 900

    def test_advanced_blueprint_monitor_and_alert_defaults(self) -> None:
        result = fill_blueprint(
            "financial_monitor_advanced",
            {
                "time": "09:00",
                "weekdays": "weekdays",
                "watchlist": "BTC,ETH,SOL",
                "signal_rules": "price + funding + sentiment",
                "portfolio_context": "",
            },
        )
        assert result is not None
        assert result.job_type == "agent"
        assert result.session_target == "daily"
        assert result.deduplicate is True
        assert result.skip_if_active is True
        assert result.timeout_seconds == 240
        assert result.monitor_config is not None
        assert result.monitor_config.monitor_type == "hash"
        assert result.monitor_config.ttl_days == 14
        assert result.failure_alert is not None
        assert result.failure_alert.after == 2

    def test_simple_blueprint_validates_bounds(self) -> None:
        with pytest.raises(BlueprintFillError, match="lower_bound must be less than upper_bound"):
            fill_blueprint(
                "financial_monitor_simple",
                {
                    "time": "08:00",
                    "weekdays": "weekdays",
                    "asset": "bitcoin",
                    "quote_currency": "usd",
                    "lower_bound": "70000",
                    "upper_bound": "70000",
                    "source": "coingecko",
                },
            )

    def test_simple_blueprint_rejects_invalid_asset(self) -> None:
        with pytest.raises(BlueprintFillError, match="asset must match"):
            fill_blueprint(
                "financial_monitor_simple",
                {
                    "time": "08:00",
                    "weekdays": "weekdays",
                    "asset": "btc\";print(1)#",
                    "quote_currency": "usd",
                    "lower_bound": "50000",
                    "upper_bound": "70000",
                    "source": "coingecko",
                },
            )


class TestFillBlueprint:
    """General fill_blueprint tests."""

    def test_unknown_blueprint_returns_none(self) -> None:
        assert fill_blueprint("nonexistent_id", {}) is None

    def test_fill_uses_defaults_when_no_values_provided(self) -> None:
        skip_required_empty = {
            "custom_reminder",
            "competitor_watch",
            "social_media_watch",
        }
        for bp in BUILTIN_BLUEPRINTS:
            if bp.id in skip_required_empty:
                continue
            result = fill_blueprint(bp.id, {})
            assert result is not None, f"fill_blueprint failed for {bp.id}"
            assert result.prompt, f"Empty prompt for {bp.id}"

    def test_name_uses_localized_title_not_prompt_truncation(self) -> None:
        result = fill_blueprint("morning_briefing", {"time": "08:00", "weekdays": "everyday"}, locale="zh")
        assert result is not None
        assert result.name == "每日早报"

    def test_empty_required_text_slot_raises(self) -> None:
        with pytest.raises(BlueprintFillError, match="message"):
            fill_blueprint("custom_reminder", {"time": "09:00", "message": ""})

    def test_empty_competitors_raises(self) -> None:
        with pytest.raises(BlueprintFillError, match="competitors"):
            fill_blueprint("competitor_watch", {"time": "09:00", "day": "1", "competitors": ""})


class TestSocialMediaWatchBlueprint:
    """social_media_watch optional keywords slot."""

    def test_keywords_optional_allows_empty(self) -> None:
        result = fill_blueprint(
            "social_media_watch",
            {
                "time": "09:00",
                "weekdays": "weekdays",
                "brand": "Myrm",
                "platforms": "Xiaohongshu, Weibo",
                "keywords": "",
            },
        )
        assert result is not None
        assert "Myrm" in result.prompt

    def test_keywords_slot_marked_optional(self) -> None:
        bp = get_blueprint("social_media_watch")
        assert bp is not None
        keywords = next(s for s in bp.slots if s.name == "keywords")
        assert keywords.optional is True

    def test_brand_slot_required(self) -> None:
        bp = get_blueprint("social_media_watch")
        assert bp is not None
        brand = next(s for s in bp.slots if s.name == "brand")
        assert brand.optional is False

    def test_empty_brand_raises(self) -> None:
        with pytest.raises(BlueprintFillError, match="brand"):
            fill_blueprint(
                "social_media_watch",
                {
                    "time": "09:00",
                    "weekdays": "weekdays",
                    "brand": "",
                    "platforms": "Xiaohongshu, Weibo",
                    "keywords": "",
                },
            )

    def test_omitted_keywords_uses_empty_default(self) -> None:
        result = fill_blueprint(
            "social_media_watch",
            {
                "time": "09:00",
                "weekdays": "weekdays",
                "brand": "Myrm",
                "platforms": "Xiaohongshu, Weibo",
            },
        )
        assert result is not None
        assert "Myrm" in result.prompt


class TestToolDescription:
    """Test get_blueprints_for_tool_description output."""

    def test_includes_read_it_later(self) -> None:
        desc = get_blueprints_for_tool_description("en")
        assert "read_it_later" in desc

    def test_output_is_concise(self) -> None:
        desc = get_blueprints_for_tool_description("en")
        lines = desc.strip().split("\n")
        assert len(lines) == len(BUILTIN_BLUEPRINTS) + 1

    def test_tool_description_marks_optional_slots(self) -> None:
        desc = get_blueprints_for_tool_description("en")
        assert "keywords?" in desc
        assert "brand?" not in desc

    def test_tool_description_uses_japanese_title_when_available(self) -> None:
        desc = get_blueprints_for_tool_description("ja")
        assert "モーニングブリーフィング" in desc
        assert "morning_briefing" in desc
