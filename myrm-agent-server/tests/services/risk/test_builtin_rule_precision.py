"""What the built-in risk rules hold and what they let through, on text people actually send to an assistant.

A rule that holds everyday messages is switched off by its users, which leaves nothing holding the secrets: the rules that
start enabled must pass ordinary chat and code and still hold every credential shape.
"""

from __future__ import annotations

import pytest
import regex
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.risk.schemas import RuleCreateRequest
from app.database.models import RiskHit, RiskRule
from app.services.risk.builtin_rules import builtin_risk_rules
from app.services.risk.constants import DEFAULT_ENABLED_CATEGORIES, RiskCategory
from app.services.risk.detection import POSITION_SUMMARY_PREFIX, TIMED_OUT_SUMMARY, RiskDetectionService
from app.services.risk.match_checks import is_confirmed_match
from app.services.risk.rule_service import RiskRuleService, RuleValidationError

from .conftest import EngineBuilder

_ALNUM = "aB3dE5fG7hJ9kL2mN4pQ6rS8tU0vW1xY"
_URLSAFE = _ALNUM + "_-"


def _token(length: int, alphabet: str = _ALNUM) -> str:
    return (alphabet * (length // len(alphabet) + 1))[:length]


EVERYDAY_TEXT = [
    "Let's schedule the meeting for tomorrow at 3pm",
    "Draft an agenda for the team meeting about our private beta launch",
    "The cookie recipe needs two eggs",
    "Which cookie does the session use?",
    "What does the authorization header carry?",
    "how do I rotate an access_token in OAuth?",
    "Explain what a JWT is and how refresh_token rotation works",
    "Set SECRET_KEY in your .env file before starting",
    "what does the DATABASE_URL variable look like",
    "The password field must be at least 8 chars",
    "How do I connect to redis://localhost:6379 from Python?",
    "My local db is postgres://localhost:5432/mydb, how do I list tables?",
    "the sk-learn style 'sk-' prefix is used by many libs",
    "https://example.com/blog/task-management-best-practices-for-remote-teams-in-2025",
    "see disk-encryption-settings-enabled-by-default-in-the-latest-version-of-the-os-release-notes",
    "ask-me-anything-about-the-new-product-roadmap-and-q3-goals-before-friday-afternoon",
    "MainApplicationContext.config.getApplicationContextBeanFactory(arg)",
    "commit 9fceb02d0ae598e95dc970b74767f19372d61af8 fixes the flaky test",
    "请帮我整理这份会议纪要,并给 zhang.wei@example.com 写邮件,手机号 13812345678",
    "我家路由器是 192.168.1.1,怎么改 Wi-Fi 密码?",
    "-----BEGIN PGP PUBLIC KEY BLOCK----- 是什么格式?",
    "apiVersion: v1\nkind: Service\nmetadata:\n  name: web\nspec:\n  ports:\n  - port: 80",
    "git clone https://github.com/user/repo.git && cd repo",
]

CODE_THAT_NAMES_SECRETS = [
    "password = input('Enter: ')",
    'api_key = os.environ["OPENAI_API_KEY"]',
    "token = requests.post(url, json=data).json()['token']",
    "access_token = response.json()['access_token']",
    "secret = config.secret_value",
    "token: required",
    "password: ********",
    "API_KEY=YOUR_API_KEY_HERE",
    "token = 4096",
    "set max token: 4096 please",
    "password=${DB_PASSWORD}",
    "password: your-password-here",
    "client_secret = settings.CLIENT_SECRET",
    "SECRET_KEY = os.environ.get('SECRET_KEY')",
    "headers = {'Authorization': f'Bearer {token}'}",
    "Authorization: Bearer <your-token>",
]

CREDENTIALS = {
    "openai project key": "key is sk-proj-" + _token(150, _URLSAFE),
    "openai legacy key": "my key sk-" + _token(48),
    "openai-compatible relay key": "key: sk-" + _token(32),
    "anthropic key": "sk-ant-api03-" + _token(93, _URLSAFE),
    "github token": "token ghp_" + _token(36),
    "github fine-grained token": "github_pat_" + _token(40, _URLSAFE),
    "aws access key": "aws AKIA" + _token(16, _ALNUM.upper()),
    "slack token": "xoxb-123456789012-123456789012-" + _token(24),
    "google api key": "AIza" + _token(35, _URLSAFE),
    "stripe live key": "sk_live_" + _token(30),
    "gitlab token": "glpat-" + _token(20, _URLSAFE),
    "password with colon": "password: hunter22xx",
    "password with equals": "my password=Zk9#mango42",
    "quoted password": "pwd = 'S3cretPassw0rd!'",
    "json password": '{"password": "Zk9#mango42x"}',
    "api key assignment": "api_key=a8f3c9d1e7b24f6a9c0d1e2f3a4b5c6d",
    "client secret": 'client_secret = "9aF3kLm2Qx7Rt5Vb8Nc1"',
    "env secret": "SECRET_KEY=8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a",
    "session id": "sessionid=9f8e7d6c5b4a3210fedcba",
    "java session cookie": "Cookie: JSESSIONID=9f8e7d6c5b4a3210fedcba",
    "bearer header": "Authorization: Bearer " + _token(40, _URLSAFE),
    "refresh token json": '{"refresh_token": "' + _token(40, _URLSAFE) + '"}',
    "postgres url": "DATABASE_URL=postgres://admin:S3cret!pw@db.internal:5432/app",
    "redis url without user": "redis://:p4ssw0rd@cache.internal:6379/0",
    "mongodb srv url": "mongodb+srv://user:Pa55w0rd@cluster0.mongodb.net/test",
    "jwt": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"),
    "private key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA",
    "kubeconfig": "apiVersion: v1\nkind: Config\nclusters:\n- cluster:\n    server: https://10.0.0.1",
}


def _hits(service: RiskDetectionService, text: str) -> set[str]:
    return {match.rule_id for match in service.detect(text).matches}


async def test_only_credential_rules_start_enabled(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as db:
        await RiskRuleService().seed_builtin_rules(db)
        await db.commit()
        rules = (await db.execute(select(RiskRule))).scalars().all()

    assert {rule.rule_id for rule in rules if rule.is_enabled} == {
        str(seed["rule_id"]) for seed in builtin_risk_rules() if seed["category"] in DEFAULT_ENABLED_CATEGORIES
    }
    assert {rule.category for rule in rules if rule.is_enabled} == {RiskCategory.SECURITY}
    assert sum(1 for rule in rules if rule.is_enabled) == 8


@pytest.mark.parametrize("text", EVERYDAY_TEXT + CODE_THAT_NAMES_SECRETS)
async def test_everyday_text_and_code_pass_the_default_rules(build_engine: EngineBuilder, text: str) -> None:
    assert not _hits(await build_engine(), text)


@pytest.mark.parametrize("text", CREDENTIALS.values(), ids=CREDENTIALS.keys())
async def test_every_credential_shape_is_held_by_the_default_rules(build_engine: EngineBuilder, text: str) -> None:
    assert (await build_engine()).detect(text).blocked


@pytest.mark.parametrize(
    "text",
    [
        "the private meeting is about printing the string with an agenda",
        "elevators, Canadian vacations, Rwanda, tinder and tint",
        "the directory structure of my project folder",
    ],
)
async def test_a_keyword_rule_does_not_match_inside_a_longer_word(build_engine: EngineBuilder, text: str) -> None:
    assert not {rule for rule in _hits(await build_engine(enable_all=True), text) if rule.endswith("_keywords")}


@pytest.mark.parametrize(
    ("text", "rule_id"),
    [
        ("请看contract文件", "contract_quote_keywords"),
        ("check the contracts and the tickets", "contract_quote_keywords"),
        ("what is the tin number", "invoice_tax_keywords"),
        ("Our VAT number is DE123456789", "invoice_tax_keywords"),
        ("please sign the NDA first", "legal_document_keywords"),
        ("quarterly budget and revenues", "financial_metrics_keywords"),
        ("附上本月薪资表", "salary_hr_keywords"),
    ],
)
async def test_a_keyword_rule_matches_the_whole_word_and_chinese_anywhere(
    build_engine: EngineBuilder, text: str, rule_id: str
) -> None:
    assert rule_id in _hits(await build_engine(enable_all=True), text)


async def test_a_hit_names_where_the_match_lies_and_not_what_it_is(build_engine: EngineBuilder) -> None:
    key = "sk-" + _token(40)
    text = f"use {key} here"

    result = (await build_engine()).detect(text)

    assert [(m.rule_id, m.match_summary) for m in result.matches] == [("api_key_like", f"chars:4-{4 + len(key)}")]
    assert key not in result.matches[0].match_summary


def test_a_pattern_without_a_value_group_has_nothing_to_check() -> None:
    match = regex.search(r"password", "password")
    assert match is not None
    assert is_confirmed_match("credential_assignment", match)


async def test_legacy_hit_text_is_cleared_and_new_summaries_are_kept(session_factory: async_sessionmaker[AsyncSession]) -> None:
    summaries = ["sk-proj-abc123", "13812345678", "", f"{POSITION_SUMMARY_PREFIX}3-9", TIMED_OUT_SUMMARY]
    async with session_factory() as db:
        for summary in summaries:
            db.add(RiskHit(trace_id="t", rule_id="r", rule_name="R", severity="high", action="block", match_summary=summary))
        await db.commit()

    service = RiskRuleService()
    async with session_factory() as db:
        first = await service.clear_legacy_hit_text(db)
        second = await service.clear_legacy_hit_text(db)
        stored = (await db.execute(select(RiskHit.match_summary).order_by(RiskHit.id))).scalars().all()

    assert (first, second) == (2, 0)
    assert stored == ["", "", "", "chars:3-9", TIMED_OUT_SUMMARY]


async def test_a_rule_stored_with_the_removed_allow_action_becomes_a_disabled_block_rule(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        db.add(RiskRule(rule_id="legacy", display_name="L", pattern="x", severity="low", action="allow", is_enabled=True))
        db.add(RiskRule(rule_id="current", display_name="C", pattern="y", severity="low", action="block", is_enabled=True))
        await db.commit()

    service = RiskRuleService()
    async with session_factory() as db:
        first = await service.disable_legacy_allow_rules(db)
        second = await service.disable_legacy_allow_rules(db)
        rules = {rule.rule_id: (rule.action, rule.is_enabled) for rule in (await db.execute(select(RiskRule))).scalars()}

    assert (first, second) == (1, 0)
    assert rules == {"legacy": ("block", False), "current": ("block", True)}


async def test_block_is_the_only_action_a_rule_can_have(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as db:
        with pytest.raises(RuleValidationError, match="Invalid action 'allow'"):
            await RiskRuleService().create_rule(db, rule_id="x", display_name="X", pattern="x", severity="low", action="allow")


def test_the_api_refuses_an_action_other_than_block() -> None:
    with pytest.raises(ValidationError):
        RuleCreateRequest(rule_id="x", display_name="X", pattern="x", severity="low", action="allow")
