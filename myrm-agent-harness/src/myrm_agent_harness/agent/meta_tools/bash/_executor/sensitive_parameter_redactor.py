"""敏感参数脱敏器 - 用于命令参数脱敏

[INPUT]

[OUTPUT]
- SensitiveParameterRedactor: 参数脱敏器类

[POS]
Command parameter redactor. Automatically redacts named sensitive parameters (--token, --password, --api-key, KEY=value) when logging commands to audit trails; the command text is otherwise left as written.

"""

import re
from typing import ClassVar


class SensitiveParameterRedactor:
    """敏感参数脱敏器

    在记录命令时自动脱敏敏感参数值，防止凭证泄露到审计日志。
    """

    # 默认敏感参数关键词
    DEFAULT_SENSITIVE_KEYWORDS: ClassVar[list[str]] = [
        "token",
        "password",
        "passwd",
        "pwd",
        "api_key",
        "apikey",
        "api-key",
        "secret",
        "key",
        "auth",
        "credential",
        "credentials",
        "access_key",
        "access-key",
        "private_key",
        "private-key",
        "bearer",
        "authorization",
    ]

    def __init__(self, custom_keywords: list[str] | None = None):
        """初始化脱敏器

        Args:
            custom_keywords: 自定义敏感关键词列表（可选）
        """
        self.sensitive_keywords = set(self.DEFAULT_SENSITIVE_KEYWORDS)
        if custom_keywords:
            self.sensitive_keywords.update(k.lower() for k in custom_keywords)

        # 构建敏感参数正则模式，匹配形式：
        # 1. --token=value / --token value / --token="value"
        # 2. env VAR=value（环境变量）
        # 短选项（-t value）的值没有名字可依据，由共享脱敏器按命令名锚定的规则处理，这里不猜。
        keywords_pattern = "|".join(re.escape(k) for k in self.sensitive_keywords)
        self._long_option_pattern = re.compile(rf"--({keywords_pattern})[=\s]+([\"']?)([^\s\"']+)\2", re.IGNORECASE)
        self._assignment_pattern = re.compile(rf"({keywords_pattern})[=]([\"']?)([^\s\"']+)\2", re.IGNORECASE)

    def redact(self, command: str) -> str:
        """脱敏命令中的敏感参数；空白与换行原样保留

        Args:
            command: 要脱敏的命令

        Returns:
            脱敏后的命令
        """
        if not command or not isinstance(command, str):
            return command

        redacted = self._long_option_pattern.sub(lambda m: f"--{m.group(1)}=***REDACTED***", command)
        return self._assignment_pattern.sub(lambda m: f"{m.group(1)}=***REDACTED***", redacted)
