"""The password-phrase rule: a password said in a sentence is held, what only talks about passwords is not.

The assignment rules read ``password = value``; people also write "my password is ..." and "密码是 ...". The rule holds the
password the harness heuristic finds beside a credential keyword, and sets aside what a reader is told to fill in, a pointer
into a secret store, and the one-time codes a user hands an agent to finish a login.
"""

from __future__ import annotations

import pytest

from app.services.risk.constants import INLINE_DETECT_CHARS
from app.services.risk.detection import RiskDetectionService
from app.services.risk.match_checks import PASSWORD_PHRASE_RULE_ID

from .conftest import EngineBuilder

# A password said in a sentence, with nothing like ``key = value`` around it.
PASSWORDS_IN_PROSE = {
    "zh-prose": "帮我连数据库，密码是 Summer2024!，写个连接脚本",
    "zh-label": "服务器 root 口令：Xk3!9vQz7mAb 帮我登录看日志",
    "zh-no-connector": "帮我登录，账号 admin 密码 Summer2024!",
    "en-prose": "my password is Xk3!9vQz7mAb, please write the connect script",
    "en-change": "change my password to Summer2024! on the staging box",
    "markdown-bold": "The staging password is **Zk9#mango42** - keep it safe",
}

# Talk about passwords, code that names one, references to where one is kept, and the values a document asks a reader to
# fill in.
NOT_PASSWORDS = {
    "strength-function": "帮我写一个密码强度校验函数，要求至少8位",
    "reset-question": "how do I reset my password on GitHub?",
    "forgot": "忘记密码了怎么办",
    "field-check": "请检查 password 字段是否为空",
    "hashing": "请解释 password hashing 里 bcrypt 和 argon2 的区别",
    "code": "def check_password(password: str) -> bool:\n    return len(password) >= 8",
    "env-pointer": "my password is env:DB_PASS",
    "vault-pointer": "password: vault:secret/data/db#password",
    "placeholder-word": "set password=your_password_here in the .env file",
    "placeholder-value": "my password is YourSecurePassword123!",
    "mask": "我的密码是 ******",
}

# A one-time code is worthless a minute later, and users hand it to an agent so that it can finish a login.
ONE_TIME_CODES = {
    "zh-sms": "你的验证码是 582013，帮我填进去",
    "en-otp": "The OTP code is 582013, enter it for me",
    "pin": "The staging PIN is 482913.",
}


def _hits(service: RiskDetectionService, text: str) -> set[str]:
    return {match.rule_id for match in service.detect(text).matches}


@pytest.mark.parametrize("text", PASSWORDS_IN_PROSE.values(), ids=PASSWORDS_IN_PROSE.keys())
async def test_a_password_said_in_a_sentence_is_held(build_engine: EngineBuilder, text: str) -> None:
    assert _hits(await build_engine(), text) == {PASSWORD_PHRASE_RULE_ID}


@pytest.mark.parametrize("text", NOT_PASSWORDS.values(), ids=NOT_PASSWORDS.keys())
async def test_talk_about_passwords_and_references_to_them_pass(build_engine: EngineBuilder, text: str) -> None:
    assert not _hits(await build_engine(), text)


@pytest.mark.parametrize("text", ONE_TIME_CODES.values(), ids=ONE_TIME_CODES.keys())
async def test_a_one_time_code_passes(build_engine: EngineBuilder, text: str) -> None:
    assert not _hits(await build_engine(), text)


async def test_the_hit_names_where_the_password_lies_and_never_repeats_it(build_engine: EngineBuilder) -> None:
    text = PASSWORDS_IN_PROSE["en-prose"]
    start = text.index("Xk3!")

    (match,) = (await build_engine()).detect(text).matches

    assert match.match_summary == f"chars:{start}-{start + len('Xk3!9vQz7mAb')}"
    assert "Xk3!" not in match.match_summary


async def test_a_password_after_other_keywords_is_still_found(build_engine: EngineBuilder) -> None:
    """The heuristic judges the text once: keywords that hold no password do not hide the one that follows them."""
    text = "password reset steps. " * 50 + "my password is Xk3!9vQz7mAb"

    assert _hits(await build_engine(), text) == {PASSWORD_PHRASE_RULE_ID}


async def test_a_text_without_a_credential_keyword_is_not_read_by_the_heuristic(build_engine: EngineBuilder) -> None:
    assert not _hits(await build_engine(), "Zk9#mango42 is a string, and so is Xk3!9vQz7mAb")


async def test_a_pasted_document_longer_than_the_inline_limit_is_left_to_the_other_rules(
    build_engine: EngineBuilder,
) -> None:
    """The heuristic holds the interpreter lock, so it reads only a text short enough to be checked in place."""
    filler = "x " * (INLINE_DETECT_CHARS // 2)
    service = await build_engine()

    assert _hits(service, "my password is Xk3!9vQz7mAb " + filler) == set()
    assert _hits(service, "password = Xk3!9vQz7mAb " + filler) == {"credential_assignment"}


async def test_an_assignment_is_held_by_the_assignment_rule_first(build_engine: EngineBuilder) -> None:
    assert _hits(await build_engine(), "password=Xk3!9vQz7mAb") == {"credential_assignment"}
