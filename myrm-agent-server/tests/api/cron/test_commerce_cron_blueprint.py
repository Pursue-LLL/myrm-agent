"""Tests for commerce morning digest cron blueprint.

Verifies:
1. `commerce_morning_digest` blueprint exists in BUILTIN_BLUEPRINTS registry.
2. Slot schema validation (store_name, time, weekdays).
3. Schedule generation conforms to cron format.
4. Bilingual prompt interpolation works cleanly for both English and Chinese.
"""

from __future__ import annotations

from app.core.cron.blueprints import fill_blueprint, get_blueprint


def test_commerce_morning_digest_blueprint_exists() -> None:
    bp = get_blueprint("commerce_morning_digest")
    assert bp is not None
    assert bp.id == "commerce_morning_digest"
    assert bp.category == "commerce"
    assert "Daily Commerce Morning Digest" in bp.title["en"]
    assert "店铺经营晨报与全盘诊断" in bp.title["zh"]

    slot_names = [s.name for s in bp.slots]
    assert "store_name" in slot_names
    assert "time" in slot_names
    assert "weekdays" in slot_names


def test_fill_commerce_blueprint_default_values() -> None:
    bp = get_blueprint("commerce_morning_digest")
    assert bp is not None

    result = fill_blueprint("commerce_morning_digest", {}, locale="en")
    assert result is not None
    assert result.schedule.expr == "30 8 * * *"
    assert "Flagship Store" in result.prompt
    assert "review yesterday's GMV" in result.prompt
    assert result.name == "Daily Commerce Morning Digest"


def test_fill_commerce_blueprint_custom_values_zh() -> None:
    bp = get_blueprint("commerce_morning_digest")
    assert bp is not None

    custom_values = {
        "store_name": "华东旗舰一号店",
        "time": "09:00",
        "weekdays": "weekdays",
    }
    result = fill_blueprint("commerce_morning_digest", custom_values, locale="zh")
    assert result is not None
    assert result.schedule.expr == "0 9 * * 1-5"
    assert "华东旗舰一号店" in result.prompt
    assert "汇总分析销售额(GMV)" in result.prompt
    assert result.name == "店铺经营晨报与全盘诊断"
