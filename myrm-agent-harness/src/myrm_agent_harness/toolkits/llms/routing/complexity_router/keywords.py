"""路由关键词、简单指示词与 judge 系统提示。

[POS]
complexity_router 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MATH_RE = re.compile(r"\\(?:frac|sum|int|sqrt|lim|infty|partial|nabla|theta|alpha|beta|gamma)")
_LATEX_BLOCK_RE = re.compile(r"\$\$.+?\$\$|\\\[.+?\\\]", re.DOTALL)
_TRACEBACK_RE = re.compile(
    r"Traceback \(most recent call last\)|"
    r"(?:File\s+\".+?\",\s+line\s+\d+)|"
    r"(?:(?:TypeError|ValueError|KeyError|AttributeError|ImportError|RuntimeError"
    r"|IndexError|NameError|FileNotFoundError|PermissionError|OSError"
    r"|ConnectionError|TimeoutError|ModuleNotFoundError|ZeroDivisionError"
    r"|StopIteration|AssertionError|NotImplementedError|RecursionError"
    r"|SyntaxError|IndentationError):\s+.+)"
)

DEFAULT_STANDARD_KEYWORDS: frozenset[str] = frozenset(
    {
        "refactor",
        "重构",
        "implement",
        "implements",
        "optimize",
        "optimized",
        "debug",
        "调试",
        "migrate",
        "迁移",
        "deploy",
        "部署",
        "analyze",
        "分析",
        "review",
        "审查",
        "security",
        "performance",
        "性能",
        "database",
        "数据库",
        "infrastructure",
        "基础设施",
        "integration",
        "集成",
        "pipeline",
        "管道",
        "middleware",
        "中间件",
        "authentication",
        "authorization",
        "error",
        "bug",
        "exception",
        "traceback",
        "报错",
        "failed",
        "失败",
        "production",
        "生产",
        "rollback",
        "回滚",
    }
)

DEFAULT_REASONING_KEYWORDS: frozenset[str] = frozenset(
    {
        "prove",
        "proof",
        "证明",
        "derive",
        "derivation",
        "推导",
        "theorem",
        "定理",
        "lemma",
        "引理",
        "corollary",
        "推论",
        "calculate",
        "compute",
        "equation",
        "方程",
        "step by step",
        "逐步",
        "chain of thought",
        "思维链",
        "architect",
        "架构",
        "system design",
        "系统设计",
        "algorithm design",
        "算法设计",
        "complexity analysis",
        "复杂度分析",
        "formal verification",
        "形式化验证",
        "root cause",
        "根因",
        "architecture design",
        "架构设计",
    }
)

DEFAULT_SIMPLE_INDICATORS: frozenset[str] = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "你好",
        "谢谢",
        "好",
        "嗯",
        "是",
        "对",
    }
)

DEFAULT_JUDGE_SYSTEM_PROMPT = (
    "You are a task complexity classifier. Classify the user's message into exactly one tier.\n"
    "SIMPLE = casual chat, short Q&A, greetings, simple factual questions\n"
    "STANDARD = coding, analysis, multi-step tasks, general technical questions\n"
    "REASONING = mathematical proofs, logical derivations, complex algorithms, system architecture design\n"
    "Rules:\n"
    "- When unsure, pick STANDARD\n"
    "- Short prompts with no technical depth → SIMPLE\n"
    "- Tasks requiring deep logical reasoning or formal proofs → REASONING\n"
    "- Queries requiring real-time data, external tools, web search, or file operations (e.g., weather, news, run code) MUST be STANDARD\n"
    'Output ONLY the raw JSON: {"tier":"SIMPLE"} or {"tier":"STANDARD"} or {"tier":"REASONING"}'
)
