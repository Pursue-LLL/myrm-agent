"""Built-in risk rules and the detection engine against a real SQLite engine.

The channel gate runs ``detect`` on the event loop, on text any chat sender controls: the built-in personal-data rules
must read data the way the privacy classifier does, and no rule may stall the loop for longer than its time budget.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import RiskRule
from app.services.risk import detection
from app.services.risk.constants import builtin_risk_rules
from app.services.risk.detection import RiskDetectionService, compile_pattern
from app.services.risk.rule_service import RiskRuleService, RuleValidationError

_TIMED_OUT = "(matching timed out)"
_STUCK_PATTERN = r"(a|aa)+$"
_STUCK_TEXT = "a" * 60 + "!"


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'risk.db'}", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(RiskRule.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _engine_over(session_factory: async_sessionmaker[AsyncSession], *, seed_builtins: bool = True) -> RiskDetectionService:
    service = RiskDetectionService()
    async with session_factory() as db:
        if seed_builtins:
            await RiskRuleService().seed_builtin_rules(db)
            await db.commit()
        await service.reload(db)
    return service


def _hit_rules(service: RiskDetectionService, text: str) -> set[str]:
    return {match.rule_id for match in service.detect(text).matches}


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("身份证 11010519491231002X", "cn_id_card"),
        ("联系 13800138000 谢谢", "cn_mobile_number"),
        ("contact alice.smith@corp.io please", "email_address"),
        ("银行卡号 6222 0200 1234 5678 901", "bank_card_context"),
        ("credit card: 4532015112830366", "bank_card_context"),
    ],
)
async def test_personal_data_is_a_hit(session_factory: async_sessionmaker[AsyncSession], text: str, rule_id: str) -> None:
    assert rule_id in _hit_rules(await _engine_over(session_factory), text)


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("订单号 1380013800123456 已发货", "cn_mobile_number"),
        ("请求 id 20261014123045123 完成", "cn_mobile_number"),
        ("编号 123456789012345678 的记录", "cn_id_card"),
        ("see user@example.com for a sample", "email_address"),
        ("bank card 2026-10-14 12-30-45 expires", "bank_card_context"),
        ("account number 12345678901234 for the invoice", "bank_card_context"),
    ],
)
async def test_what_only_looks_like_personal_data_is_not_a_hit(
    session_factory: async_sessionmaker[AsyncSession], text: str, rule_id: str
) -> None:
    assert rule_id not in _hit_rules(await _engine_over(session_factory), text)


async def test_a_long_dotted_run_does_not_stall_the_email_rule(session_factory: async_sessionmaker[AsyncSession]) -> None:
    service = await _engine_over(session_factory)

    started = time.perf_counter()
    hits = _hit_rules(service, "a." * 20_000)

    assert time.perf_counter() - started < 2  # the unbounded address pattern took ~11 s on this text
    assert "email_address" not in hits


def test_every_builtin_pattern_is_usable() -> None:
    for rule in builtin_risk_rules():
        compile_pattern(str(rule["pattern"]))


async def test_a_backtracking_custom_rule_holds_the_text_instead_of_stalling(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(detection, "MATCH_TIMEOUT_SECONDS", 0.05)
    async with session_factory() as db:
        await RiskRuleService().create_rule(
            db, rule_id="stuck", display_name="Stuck", pattern=_STUCK_PATTERN, severity="high", action="block"
        )
        await db.commit()
    service = await _engine_over(session_factory, seed_builtins=False)

    started = time.perf_counter()
    result = service.detect(_STUCK_TEXT)

    assert time.perf_counter() - started < 5
    assert result.blocked
    assert [(m.rule_id, m.match_summary) for m in result.matches] == [("stuck", _TIMED_OUT)]


async def test_a_pattern_too_large_to_build_is_refused_and_skipped(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as db:
        with pytest.raises(RuleValidationError, match="too large"):
            await RiskRuleService().create_rule(
                db, rule_id="huge", display_name="Huge", pattern="a{99999999}", severity="low", action="block"
            )
        db.add(RiskRule(rule_id="stored-huge", display_name="Stored", pattern="a{99999999}", severity="low", action="block"))
        await db.commit()

    started = time.perf_counter()
    service = await _engine_over(session_factory, seed_builtins=False)

    assert time.perf_counter() - started < 5
    assert service.rule_count == 0


def test_preview_reports_the_matched_text_as_detect_would() -> None:
    pattern = r"\b(sk-[a-z0-9]{12,}|AKIA[0-9A-Z]{16})\b"
    snippets = RiskDetectionService().detect_preview("key sk-abcdefghijkl1 and AKIAABCDEFGHIJKLMNOP", pattern)
    assert snippets == ["sk-abcdefghijkl1", "AKIAABCDEFGHIJKLMNOP"]


def test_preview_refuses_a_pattern_that_cannot_finish_the_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detection, "MATCH_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(ValueError, match="too long"):
        RiskDetectionService().detect_preview(_STUCK_TEXT, _STUCK_PATTERN)


def test_preview_names_what_is_wrong_with_a_pattern() -> None:
    with pytest.raises(ValueError, match="Invalid regex pattern"):
        RiskDetectionService().detect_preview("x", "([")


async def test_seeding_refreshes_the_pattern_of_a_stored_builtin_rule_and_keeps_what_the_user_set(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        db.add(
            RiskRule(
                rule_id="email_address",
                display_name="My e-mail rule",
                pattern=r"\S+@\S+",
                severity="low",
                action="allow",
                category="personal",
                is_enabled=False,
                is_builtin=True,
                sort_order=10,
            )
        )
        db.add(RiskRule(rule_id="mine", display_name="Mine", pattern="x", severity="low", action="allow", is_builtin=False))
        await db.commit()

    service = RiskRuleService()
    async with session_factory() as db:
        inserted = await service.seed_builtin_rules(db)
        await db.commit()
        again = await service.seed_builtin_rules(db)
        email = await service.get_rule(db, "email_address")
        mine = await service.get_rule(db, "mine")

    expected = next(rule["pattern"] for rule in builtin_risk_rules() if rule["rule_id"] == "email_address")
    assert inserted == len(builtin_risk_rules()) - 1
    assert again == 0
    assert email is not None
    assert email.pattern == expected
    assert (email.display_name, email.severity, email.action, email.is_enabled) == ("My e-mail rule", "low", "allow", False)
    assert mine is not None
    assert mine.pattern == "x"
