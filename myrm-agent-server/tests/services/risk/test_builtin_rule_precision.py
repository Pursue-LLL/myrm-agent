"""What the built-in risk rules hold and what they let through, on text people actually send to an assistant.

A rule that holds everyday messages is switched off by its users, which leaves nothing holding the secrets: the rules that
start enabled must pass the ordinary chat and code listed here and still hold each credential listed here, and the vendor
shapes the harness identifies on their own.
"""

from __future__ import annotations

import re

import pytest
import regex
from myrm_agent_harness.core.security.detection.leak_detector import DISTINCTIVE_KEY_PATTERNS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import RiskRule
from app.services.risk.builtin_rules import builtin_risk_rules
from app.services.risk.constants import DEFAULT_ENABLED_CATEGORIES, RiskCategory
from app.services.risk.detection import RiskDetectionService
from app.services.risk.match_checks import is_confirmed_match
from app.services.risk.rule_service import RiskRuleService

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
    "Authorization: Bearer eyJhbGci...",
    'Send {"token": "sk-ant-oat01-..."} to the endpoint',
    "api_key = sk-ab\u2026wxyz",
    # A TypeScript non-null assertion still names the variable and does not carry the key.
    "const apiKey = process.env.GROQ_API_KEY!;",
    "  apiKey: process.env.GROQ_API_KEY!,",
    # The value of an assignment ends at the next query parameter and at the first full-width punctuation mark.
    "https://x.io/cb?api_key=YOUR_KEY&k=1&sig=Zk9mango42",
    "secret: isSecret\uff08N3\uff09",
    # The value a reader is told to fill in, in every spelling documentation uses.
    "password: YourSecurePassword123!",
    "api_secret = yourSecretKey2024",
    "DB_PASSWORD=ENTER_DB_PASSWORD_123",
    "SECRET_KEY=CHANGE-TO-A-UNIQUE-64-CHAR-SECRET-KEY",
    "api_key = replace_with_your_key",
    "client_secret: example-secret-value",
    # A connection string whose password is a reference or a word.
    "DATABASE_URL=postgres://app:${DB_PASSWORD}@db:5432/app",
    "postgres://user:<password>@host/db",
    "postgres://user:password@localhost/db",
    # An identifier that happens to begin with the prefix of a vendor key.
    "const vercel_deployment_inspector_url_builder = 1",
    "fal_ai_client_request_handler_configuration_object = make()",
    # A session or bearer value a reader recognises as an example: short, or made of readable words.
    '{"sessionId": "session-1"}',
    "headers = {'Authorization': 'Bearer test-token-123'}",
    "Authorization: Bearer my-example-access-token-value",
    "Cookie: sessionid=<your-session-id>",
    "Set-Cookie: sessionid=session-for-the-demo-user; Path=/",
    # A cookie header that carries nothing a session depends on.
    "Cookie: theme=dark; lang=en; _ga=GA1.2.1234567890.1234567890",
    "Set-Cookie: id=a3fWa; Expires=Thu, 21 Oct 2021 07:28:00 GMT; Secure; HttpOnly",
    # A pointer into a secret store names the secret and does not carry it.
    'api_token="env:GEMINI_API_KEY"',
    "password: vault:secret/data/db#password",
    # A placeholder word behind the prefix of a vendor key.
    'OPENAI_API_KEY="sk-YOUR_API_KEY"',
]

CREDENTIALS = {
    "openai project key": "key is sk-proj-" + _token(150, _URLSAFE),
    "openai key without a project prefix": "my key sk-" + _token(48),
    "openai-compatible relay key": "key: sk-" + _token(32),
    "key after an escaped line break": "first line\\n" + "sk-" + _token(48),
    "key after a percent-encoded equals sign": "?token%3Dsk-" + _token(48),
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
    "basic header": "Authorization: Basic dXNlcjpaazkjbWFuZ280Mnh4",
    "php session id": "PHPSESSID=8f3a9c1e5b7d2046a1c8e9f0b3d5a7c2",
    "cookie header in a curl command": "curl https://x.io/api -H 'Cookie: PHPSESSID=8f3a9c1e5b7d2046a1c8e9f0b3d5a7c2; theme=dark'",
    "session behind other cookies": "Cookie: theme=dark; lang=en; session=" + _token(32),
    "set-cookie header": "Set-Cookie: session=eyJ1c2VyIjoiYWxpY2UifQ.Zk9mango42xYpq7; Path=/; HttpOnly",
    "express session cookie": "cookie: connect.sid=s%3A" + _token(32, _URLSAFE) + ".x7Yz3Qw9",
    "session id after a cookie header on the line": "cookie: a=b then sessionid=9f8e7d6c5b4a3210fedcba",
    "password with dots inside": "password: Zk9.mango.42x",
    "refresh token json": '{"refresh_token": "' + _token(40, _URLSAFE) + '"}',
    "postgres url": "DATABASE_URL=postgres://admin:S3cret!pw@db.internal:5432/app",
    "redis url without user": "redis://:p4ssw0rd@cache.internal:6379/0",
    "mongodb srv url": "mongodb+srv://user:Pa55w0rd@cluster0.mongodb.net/test",
    "jwt": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"),
    "private key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA",
    "kubeconfig": "apiVersion: v1\nkind: Config\nclusters:\n- cluster:\n    server: https://10.0.0.1",
    "groq key in an env file": "GROQ_API_KEY=gsk_" + _token(40),
    "openai key in an env file": "OPENAI_API_KEY=sk-" + _token(48),
    "password with an env prefix": "DB_PASSWORD=Zk9#mango42x",
    "api key with a kebab prefix": "my-api-key: a8f3c9d1e7b24f6a9c0d1e2f3a4b5c6d",
    "aws secret access key": "aws_secret_access_key = " + _token(40),
    "password that begins with a placeholder word": "password: Yourdog2012!",
    "password that begins with another placeholder word": "password=Changeme2024!",
    "all-capitals password that begins with a placeholder word": "password: ENTERPRISE2012!",
    "all-capitals password that begins with another placeholder word": "DB_PASSWORD=SAMPLER99xyz",
    "all-capitals secret that begins with a third placeholder word": "SECRET_KEY=YOURMOM1234x",
    "env secret in groups of letters": "API_SECRET=ABCD-EFGH-IJKL-9999",
    "key before the next query parameter": "api_key=Zk9#mango42x&profile=x",
    "password before full-width punctuation": "password: Zk9#mango42x\uff0c\u8bf7\u4fdd\u7ba1",
    "mysql url with a query separator in the password": "mysql://root:Pa55w0rd&x=1@10.0.0.2/app",
    "password with a non-ASCII symbol": "password: p@ss\u20acword42",
}

# One sample per vendor shape the harness identifies on its own; the gate builds its pattern from that table.
_VENDOR_SAMPLES = {
    "stripe_key": "sk_test_" + _token(24),
    "stripe_restricted": "rk_live_" + _token(24),
    "openai_key": "sk-" + _token(48, _URLSAFE),
    "anthropic_key": "sk-ant-" + _token(32, _URLSAFE),
    "google_key": "AIza" + _token(35, _URLSAFE),
    "huggingface_token": "hf_" + _token(34),
    "replicate_token": "r8_" + _token(36),
    "perplexity_key": "pplx-" + _token(48),
    "groq_key": "gsk_" + _token(40),
    "aws_access_key": "AKIA" + _token(16, _ALNUM.upper()),
    "aws_session_token": "ASIA" + _token(16, _ALNUM.upper()),
    "digitalocean_token": "dop_v1_" + _token(64, "0123456789abcdef"),
    "supabase_key": "sbp_" + _token(40, "0123456789abcdef"),
    "github_token": "ghs_" + _token(36),
    "github_pat": "github_pat_" + _token(22, _URLSAFE),
    "gitlab_token": "glpat-" + _token(20, _URLSAFE),
    "npm_token": "npm_" + _token(36),
    "pypi_token": "pypi-" + _token(36, _URLSAFE),
    "slack_token": "xoxp-123456789012-" + _token(10),
    "sendgrid_key": "SG." + _token(22, _URLSAFE) + "." + _token(43, _URLSAFE),
    "tavily_key": "tvly-" + _token(32),
    "browserbase_key": "bb_live_" + _token(32),
    "shopify_token": "shpat_" + _token(32, "0123456789abcdef"),
    "shopify_shared_secret": "shpss_" + _token(32, "0123456789abcdef"),
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
async def test_every_listed_credential_is_held_by_the_default_rules(build_engine: EngineBuilder, text: str) -> None:
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


def test_every_distinctive_vendor_shape_has_a_sample() -> None:
    """A shape added to the harness's table fails here until it has a sample, and so a test that the gate holds it."""
    assert set(_VENDOR_SAMPLES) == {name for name, _ in DISTINCTIVE_KEY_PATTERNS}


@pytest.mark.parametrize(("name", "pattern"), DISTINCTIVE_KEY_PATTERNS, ids=[name for name, _ in DISTINCTIVE_KEY_PATTERNS])
async def test_every_distinctive_vendor_shape_is_held(build_engine: EngineBuilder, name: str, pattern: re.Pattern[str]) -> None:
    sample = _VENDOR_SAMPLES[name]
    assert pattern.fullmatch(sample), "the sample is not of the shape it stands for"
    assert "api_key_like" in _hits(await build_engine(), f"here it is: {sample}")
