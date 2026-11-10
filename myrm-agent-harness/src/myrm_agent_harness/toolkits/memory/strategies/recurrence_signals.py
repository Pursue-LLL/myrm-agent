"""Deterministic signals of a session summary: does it carry a must-remember fact, or is it chitchat.

[INPUT]
- none (POS: pure keyword rules)

[OUTPUT]
- is_important: the text names a health, safety or credential signal that is worth remembering on first mention
- is_trivial_summary: the text is a greeting, acknowledgment or other chitchat with no long-term memory value

[POS]
Zero-cost keyword rules the recurrence detector applies before it touches the vector store: an important signal
bypasses the recurrence threshold, trivial chitchat never enters the buffer.
"""

from __future__ import annotations

_IMPORTANCE_KEYWORDS_EN = frozenset(
    {
        "allergy",
        "allergic",
        "anaphylaxis",
        "medication",
        "prescription",
        "diabetes",
        "asthma",
        "epilepsy",
        "emergency",
        "hospital",
        "password",
        "credential",
        "deadline",
        "urgent",
        "phobia",
        "trauma",
        "intolerance",
        "wheelchair",
        "disability",
    }
)

_IMPORTANCE_KEYWORDS_CN = frozenset(
    {
        "过敏",
        "药物",
        "处方",
        "糖尿病",
        "哮喘",
        "癫痫",
        "急诊",
        "医院",
        "密码",
        "密钥",
        "凭证",
        "截止日期",
        "紧急",
        "恐惧",
        "创伤",
        "饮食禁忌",
        "不耐受",
        "残疾",
        "轮椅",
    }
)

_TRIVIAL_SUMMARY_PATTERNS = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "hi there",
        "hello there",
        "greetings",
        "good morning",
        "good afternoon",
        "good evening",
        "morning",
        "ok",
        "okay",
        "fine",
        "cool",
        "sure",
        "thanks",
        "thank you",
        "thanks a lot",
        "thank you very much",
        "thx",
        "bye",
        "goodbye",
        "test",
        "testing",
        "ping",
        "pong",
        "chat",
        "你好",
        "您好",
        "你好呀",
        "在吗",
        "在不在",
        "打个招呼",
        "问好",
        "测试",
        "哈喽",
        "嗨",
        "好的",
        "好的收到",
        "收到",
        "明白",
        "行",
        "可以",
        "谢谢",
        "多谢",
        "再见",
        "拜拜",
    }
)


def is_important(text: str) -> bool:
    """Check if text contains high-importance signals (health, safety, credentials)."""
    lower = text.lower()
    for kw in _IMPORTANCE_KEYWORDS_EN:
        if kw in lower:
            return True
    return any(kw in text for kw in _IMPORTANCE_KEYWORDS_CN)


def is_trivial_summary(text: str) -> bool:
    """Check if text is trivial conversational chitchat with no long-term memory value.

    Filters out greetings, acknowledgments, and empty chitchat unless high importance signals
    are present.
    """
    cleaned = "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()
    if not cleaned or cleaned in _TRIVIAL_SUMMARY_PATTERNS:
        return True
    return len(cleaned) <= 4 and not is_important(text)
