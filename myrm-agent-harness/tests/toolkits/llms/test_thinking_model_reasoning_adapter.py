"""Unit tests for ThinkingModelReasoningAdapter.

Validates thinking model CoT token scrubbing, reasoning content fallback extraction,
and MemoryExtractor integration.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms import ThinkingModelReasoningAdapter
from myrm_agent_harness.toolkits.memory.strategies.extractor.parse import _parse_response


class TestThinkingModelReasoningAdapter:
    """Test suite for reasoning model unpacking and <think> token scrubbing."""

    def test_scrub_thinking_tags_closed(self) -> None:
        raw = "<think>\nThinking about preferences...\nUser prefers dark mode.\n</think>\nUser preference: dark mode"
        cleaned = ThinkingModelReasoningAdapter.scrub_thinking_tags(raw)
        assert cleaned == "User preference: dark mode"

    def test_scrub_thinking_tags_unclosed(self) -> None:
        raw = "<think>\nStill reasoning and never closed..."
        cleaned = ThinkingModelReasoningAdapter.scrub_thinking_tags(raw)
        assert cleaned == ""

    def test_scrub_thought_prefix(self) -> None:
        raw = "thought: This is my internal reasoning\n\nActual response here"
        cleaned = ThinkingModelReasoningAdapter.scrub_thinking_tags(raw)
        assert cleaned == "Actual response here"

    def test_extract_effective_content_normal_content(self) -> None:
        payload = {
            "content": "<think>some thought</think>Final extracted content",
            "reasoning_content": "some thought",
        }
        res = ThinkingModelReasoningAdapter.extract_effective_content(payload)
        assert res == "Final extracted content"

    def test_extract_effective_content_fallback_to_reasoning_codeblock(self) -> None:
        # Case: content is empty, reasoning contains a markdown json block
        payload = {
            "content": "",
            "reasoning_content": (
                "Let's output the result in json:\n"
                "```json\n"
                '[{"memory_type": "semantic", "content": "Prefers Python"}]\n'
                "```"
            ),
        }
        res = ThinkingModelReasoningAdapter.extract_effective_content(payload)
        assert res == '[{"memory_type": "semantic", "content": "Prefers Python"}]'

    def test_extract_effective_content_fallback_to_embedded_json(self) -> None:
        payload = {
            "content": "",
            "reasoning": (
                "I should output memory entries now. Here is the array: "
                '[{"memory_type": "semantic", "content": "Lives in Seattle"}]'
                " That is all."
            ),
        }
        res = ThinkingModelReasoningAdapter.extract_effective_content(payload)
        assert res == '[{"memory_type": "semantic", "content": "Lives in Seattle"}]'

    def test_extract_json_block(self) -> None:
        text = "Leading noise [1, 2, 3] trailing noise"
        assert ThinkingModelReasoningAdapter.extract_json_block(text) == "[1, 2, 3]"

        obj_text = 'Noise {"key": "val"} more noise'
        assert ThinkingModelReasoningAdapter.extract_json_block(obj_text) == '{"key": "val"}'

        assert ThinkingModelReasoningAdapter.extract_json_block("No json here") is None
        assert ThinkingModelReasoningAdapter.extract_json_block("") is None


class TestExtractorIntegrationWithThinkingAdapter:
    """Test suite ensuring extractor._parse_response gracefully handles thinking model outputs."""

    def test_parse_response_with_think_tags(self) -> None:
        raw_output = (
            "<think>\n"
            "Analyzing dialogue:\n"
            "- User mentions python experience\n"
            "</think>\n"
            "```json\n"
            "[\n"
            '  {"memory_type": "semantic", "content": "Prefers Python 3.12", "confidence": 0.9}\n'
            "]\n"
            "```"
        )
        memories = _parse_response(raw_output)
        assert len(memories) == 1
        assert memories[0].content == "Prefers Python 3.12"
        assert memories[0].confidence == 0.9

    def test_parse_response_with_embedded_json_in_reasoning(self) -> None:
        raw_output = (
            "Based on the analysis, here is what I found: "
            '[{"memory_type": "semantic", "content": "User works at Acme Corp", "confidence": 0.85}]'
            " Hope this helps!"
        )
        memories = _parse_response(raw_output)
        assert len(memories) == 1
        assert memories[0].content == "User works at Acme Corp"
        assert memories[0].confidence == 0.85
