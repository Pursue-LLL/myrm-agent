"""Conversations shared by the correction propagation tests.

The user corrects the assistant, contradicts an earlier statement, corrects in Chinese, or has nothing to correct.
"""

import pytest
from dotenv import load_dotenv

load_dotenv(override=False)


@pytest.fixture()
def correction_messages() -> list[dict[str, str]]:
    """Conversation where user corrects a factual mistake."""
    return [
        {"role": "user", "content": "Tell me about our company MindForge"},
        {"role": "assistant", "content": "MindForce is an AI company that focuses on..."},
        {"role": "user", "content": "That's wrong! Our company name is MindForge, not MindForce."},
        {"role": "assistant", "content": "I apologize for the mistake. MindForge is..."},
    ]


@pytest.fixture()
def implicit_correction_messages() -> list[dict[str, str]]:
    """Conversation where user implicitly corrects without explicit negation."""
    return [
        {"role": "user", "content": "Can you help me with my work at ByteDance?"},
        {"role": "assistant", "content": "Sure! Since you work at ByteDance, I can help with..."},
        {"role": "user", "content": "Actually I left ByteDance last month. I'm at Google now."},
        {"role": "assistant", "content": "Got it, let me help you with your Google work."},
    ]


@pytest.fixture()
def no_correction_messages() -> list[dict[str, str]]:
    """Normal conversation without corrections."""
    return [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language."},
        {"role": "user", "content": "Thanks, that's helpful!"},
    ]


@pytest.fixture()
def zh_correction_messages() -> list[dict[str, str]]:
    """Chinese conversation where user corrects a mistake."""
    return [
        {"role": "user", "content": "介绍一下我们公司的产品 MindForge"},
        {"role": "assistant", "content": "MindForce 是一款..."},
        {"role": "user", "content": "你搞错了，是 MindForge 不是 MindForce"},
        {"role": "assistant", "content": "抱歉，MindForge 是..."},
    ]
