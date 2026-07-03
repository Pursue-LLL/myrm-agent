"""Unit tests for cron blueprints — verifies registry integrity and fill logic.

[POS]
Tests for the cron blueprint registry and fill_blueprint function.
"""

from __future__ import annotations

import pytest

from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintSlot,
    CronBlueprint,
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

    def test_all_blueprints_have_bilingual_titles(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            assert "en" in bp.title, f"{bp.id} missing English title"
            assert "zh" in bp.title, f"{bp.id} missing Chinese title"

    def test_all_blueprints_have_bilingual_descriptions(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            assert "en" in bp.description, f"{bp.id} missing English description"
            assert "zh" in bp.description, f"{bp.id} missing Chinese description"

    def test_all_blueprints_have_bilingual_prompts(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            assert "en" in bp.prompt_template, f"{bp.id} missing English prompt"
            assert "zh" in bp.prompt_template, f"{bp.id} missing Chinese prompt"

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


class TestFillBlueprint:
    """General fill_blueprint tests."""

    def test_unknown_blueprint_returns_none(self) -> None:
        assert fill_blueprint("nonexistent_id", {}) is None

    def test_fill_uses_defaults_when_no_values_provided(self) -> None:
        for bp in BUILTIN_BLUEPRINTS:
            result = fill_blueprint(bp.id, {})
            assert result is not None, f"fill_blueprint failed for {bp.id}"
            assert result.prompt, f"Empty prompt for {bp.id}"


class TestToolDescription:
    """Test get_blueprints_for_tool_description output."""

    def test_includes_read_it_later(self) -> None:
        desc = get_blueprints_for_tool_description("en")
        assert "read_it_later" in desc

    def test_output_is_concise(self) -> None:
        desc = get_blueprints_for_tool_description("en")
        lines = desc.strip().split("\n")
        assert len(lines) == len(BUILTIN_BLUEPRINTS) + 1
