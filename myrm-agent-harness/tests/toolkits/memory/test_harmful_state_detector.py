import pytest

from myrm_agent_harness.core.security.detection.harmful_state_detector import scan_for_harmful_states


def test_scan_for_harmful_states():
    # Test safe text
    assert scan_for_harmful_states("I am feeling a bit sad today.") == []
    assert scan_for_harmful_states("My son has ADHD.") == []

    # Test self-harm
    assert len(scan_for_harmful_states("I want to kill myself")) > 0
    assert len(scan_for_harmful_states("不想活了")) > 0

    # Test severe depression
    assert len(scan_for_harmful_states("I am completely hopeless")) > 0
    assert len(scan_for_harmful_states("自己是个废物")) > 0

    # Test paranoia
    assert len(scan_for_harmful_states("someone is following me")) > 0
    assert len(scan_for_harmful_states("脑子里有芯片")) > 0

    # Test anxiety
    assert len(scan_for_harmful_states("I am having a panic attack")) > 0
    assert len(scan_for_harmful_states("喘不过气")) > 0


@pytest.mark.parametrize(
    "text",
    [
        "我真的不想活了",
        "我最近总觉得想死",
        "用户说他不想活了，需要记住",
        "他上周自杀未遂",
        "我有重度抑郁",
        "我被人监视",
        "我快疯了",
        "工作压力大到我喘不过气",
    ],
)
def test_chinese_phrase_is_detected_inside_a_sentence(text: str) -> None:
    assert scan_for_harmful_states(text)


@pytest.mark.parametrize("text", ["我今天有点难过", "我儿子有多动症", "我喜欢吃火锅", "I like long walks"])
def test_ordinary_text_is_not_flagged(text: str) -> None:
    assert scan_for_harmful_states(text) == []


def test_english_phrases_stay_word_bounded() -> None:
    assert scan_for_harmful_states("the worthlessly long variable name") == []
    assert scan_for_harmful_states("User said: I want to die tonight")
