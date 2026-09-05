"""Test model name normalization for OpenAI/Anthropic/Gemini compatible providers."""

from app.core.channel_bridge.model_resolver import _normalize_model_name


class TestModelNameNormalization:
    """Test model name normalization for various compatible provider formats."""

    def test_openai_compatible_hyphen(self) -> None:
        """Test openai-compatible with hyphen converts to openai/."""
        result = _normalize_model_name("openai-compatible/deepseek-v4-flash")
        assert result == "openai/deepseek-v4-flash"

    def test_openai_compatible_underscore(self) -> None:
        """Test openai_compatible with underscore converts to openai/."""
        result = _normalize_model_name("openai_compatible/deepseek-v4-flash")
        assert result == "openai/deepseek-v4-flash"

    def test_anthropic_compatible_hyphen(self) -> None:
        """Test anthropic-compatible with hyphen converts to anthropic/."""
        result = _normalize_model_name("anthropic-compatible/claude-3-sonnet")
        assert result == "anthropic/claude-3-sonnet"

    def test_anthropic_compatible_underscore(self) -> None:
        """Test anthropic_compatible with underscore converts to anthropic/."""
        result = _normalize_model_name("anthropic_compatible/claude-3-sonnet")
        assert result == "anthropic/claude-3-sonnet"

    def test_gemini_compatible_hyphen(self) -> None:
        """Test gemini-compatible with hyphen converts to gemini/."""
        result = _normalize_model_name("gemini-compatible/gemini-pro")
        assert result == "gemini/gemini-pro"

    def test_gemini_compatible_underscore(self) -> None:
        """Test gemini_compatible with underscore converts to gemini/."""
        result = _normalize_model_name("gemini_compatible/gemini-pro")
        assert result == "gemini/gemini-pro"

    def test_siliconflow(self) -> None:
        """Test siliconflow converts to openai/."""
        result = _normalize_model_name("siliconflow/qwen-turbo")
        assert result == "openai/qwen-turbo"

    def test_standard_openai_format(self) -> None:
        """Test standard openai/ format remains unchanged."""
        result = _normalize_model_name("openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_standard_anthropic_format(self) -> None:
        """Test standard anthropic/ format remains unchanged."""
        result = _normalize_model_name("anthropic/claude-3-opus")
        assert result == "anthropic/claude-3-opus"

    def test_standard_gemini_format(self) -> None:
        """Test standard gemini/ format remains unchanged."""
        result = _normalize_model_name("gemini/gemini-1.5-pro")
        assert result == "gemini/gemini-1.5-pro"

    def test_bare_model_name(self) -> None:
        """Test bare model name (no slash) remains unchanged."""
        result = _normalize_model_name("gpt-4o")
        assert result == "gpt-4o"

    def test_unknown_provider(self) -> None:
        """Test unknown provider prefix remains unchanged."""
        result = _normalize_model_name("custom-provider/custom-model")
        assert result == "custom-provider/custom-model"

    def test_case_insensitive(self) -> None:
        """Test that provider prefix matching is case-insensitive."""
        result = _normalize_model_name("OpenAI-Compatible/model-name")
        assert result == "openai/model-name"

    def test_collapse_duplicated_anthropic_prefix(self) -> None:
        """Test collapsing duplicated anthropic/anthropic/ to anthropic/."""
        result = _normalize_model_name("anthropic/anthropic/claude-3-7-sonnet-20250219")
        assert result == "anthropic/claude-3-7-sonnet-20250219"

    def test_collapse_duplicated_openai_prefix(self) -> None:
        """Test collapsing duplicated openai/openai/ to openai/."""
        result = _normalize_model_name("openai/openai/gpt-4o")
        assert result == "openai/gpt-4o"

    def test_collapse_hybrid_alias_prefix(self) -> None:
        """Test collapsing hybrid alias prefixes e.g. openai-compatible/openai/."""
        result = _normalize_model_name("openai-compatible/openai/deepseek-chat")
        assert result == "openai/deepseek-chat"

    def test_deeply_nested_duplicated_prefixes(self) -> None:
        """Test collapsing multiple consecutive repeated prefixes."""
        result = _normalize_model_name("anthropic/anthropic/anthropic/claude-3-5-sonnet")
        assert result == "anthropic/claude-3-5-sonnet"

    def test_model_with_hyphenated_family_preserves_segment(self) -> None:
        """Ensure legitimate model names containing family substrings are not corruptly collapsed."""
        result = _normalize_model_name("qwen/qwen-2.5-72b-instruct")
        assert result == "qwen/qwen-2.5-72b-instruct"

    def test_consecutive_slashes_cleaned(self) -> None:
        """Ensure accidental consecutive slashes are safely normalized."""
        result = _normalize_model_name("anthropic//claude-3-5-sonnet")
        assert result == "anthropic/claude-3-5-sonnet"
        result2 = _normalize_model_name("openai///openai//gpt-4o")
        assert result2 == "openai/gpt-4o"


