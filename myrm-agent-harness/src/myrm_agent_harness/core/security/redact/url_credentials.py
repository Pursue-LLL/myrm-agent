"""URL credential detectors of the runtime redactor.

A connection string or proxy URL carries its password in the userinfo part, ``scheme://[user]:password@host``, and
tools print it in error messages, config dumps and settings files whatever the service is. Two detectors mask the
password and keep the user name and the rest of the URL readable: one for database and message-broker services,
whose findings the skill export names ``database_credential``, and one for any other scheme. A third masks a bare
token in the user position (``https://TOKEN@host``), the form of a private git remote.

Each regex names the secret by its capture group; ``engine.py`` and ``agent/skills/security/content_sanitizer.py``
read the groups by number, so a change of the layout has to be mirrored there. A password that is a variable
reference (``redis://:${REDIS_PASSWORD}@cache``, the usual compose form) is a name, not a secret, and stays readable.

[INPUT]
- patterns::_is_env_reference (POS: Compiled regex patterns, keyword guard and shared value-masking helpers of the runtime redactor)

[OUTPUT]
- ``_DB_CONNSTR_RE`` — database / broker DSN; groups: 1 = scheme, user and colon, 2 = password, 3 = ``@``
- ``_URL_USERINFO_RE`` — ``scheme://[user]:password@`` of any scheme; groups: 1 = scheme, 2 = user (may be empty), 3 = password
- ``_URL_BARE_TOKEN_RE`` — ``scheme://TOKEN@host``; groups: 1 = scheme and ``://``, 2 = token, 3 = ``@`` and the rest
- ``_redact_db_connstr`` / ``_redact_url_userinfo`` — replacers of the first two: the password becomes ``***``, a variable reference is kept

[POS]
URL credential regexes and replacers of the runtime redactor; consumed by ``engine.py`` and ``agent/skills/security/content_sanitizer.py``.
"""

from __future__ import annotations

import re

from .patterns import _is_env_reference

# 数据库与消息队列的 DSN：用户名可以为空（`redis://:password@host`），scheme 可带驱动名
# （`postgresql+asyncpg`、`mysql+pymysql`）。DB 的 DSN 先于通用规则处理，导出审查里的类别因此是 database_credential。
_DB_CONNSTR_RE = re.compile(
    r"((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|rediss?|amqps?)(?:\+[a-z0-9_]+)?://[^:]*:)([^@]+)(@)",
    re.IGNORECASE,
)

# 任意 scheme 的 `scheme://[user]:password@host`（`socks5`/`ssh`/`smtp`/`clickhouse`/`mssql+pyodbc`/`https`），
# 用户名可为空，密码段掩码，用户名保留用于可读性。负向后顾使 scheme 只从一串 scheme 字符的开头起匹配，
# 一串 scheme 字符因此只扫一次；没有它，`a` 重复一万六千次的串每个起点都扫到串尾，耗时随长度平方增长（约 1.3 秒）。
# scheme 不设长度上限：上限会让 `://` 前有 33 个以上字符的串整体漏掉，却不省任何耗时。
_URL_USERINFO_RE = re.compile(
    r"(?<![a-z0-9+.\-])([a-z][a-z0-9+.\-]*)://([^\s/@:]*):([^\s/@]+)@",
    re.IGNORECASE,
)

# `scheme://TOKEN@host`（无冒号 bare-token userinfo，如 git 私有仓库 URL）。
# 8+ 字符避免误伤短用户名。对齐 Hermes #6396。
_URL_BARE_TOKEN_RE = re.compile(
    r"((?:https?|wss?|git|ssh|ftp|ftps|sftp)://)([^\s:@/]{8,})(@[^\s]+)",
    re.IGNORECASE,
)


def _redact_db_connstr(m: re.Match[str]) -> str:
    """Replacement for ``_DB_CONNSTR_RE``: the password becomes ``***`` unless it is a variable reference."""
    if _is_env_reference(m.group(2)):
        return m.group(0)
    return f"{m.group(1)}***{m.group(3)}"


def _redact_url_userinfo(m: re.Match[str]) -> str:
    """Replacement for ``_URL_USERINFO_RE``: the password becomes ``***`` unless it is a variable reference."""
    if _is_env_reference(m.group(3)):
        return m.group(0)
    return f"{m.group(1)}://{m.group(2)}:***@"
