"""Tests for SynonymExpander"""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.skills.search.synonym_expander import (
    SynonymExpander,
)


class TestSynonymExpander:
    """Test SynonymExpander functionality"""

    def test_expand_english_synonyms(self) -> None:
        """Test English synonym expansion"""
        expander = SynonymExpander()
        expanded = expander.expand("database")
        assert "database" in expanded
        assert any("db" in q for q in expanded)

    def test_expand_chinese_synonyms(self) -> None:
        """Test Chinese synonym expansion"""
        expander = SynonymExpander()
        expanded = expander.expand("数据库")
        assert "数据库" in expanded
        assert any("database" in q or "db" in q for q in expanded)

    def test_expand_multilingual(self) -> None:
        """Test multilingual synonym expansion"""
        expander = SynonymExpander()

        # Chinese to English
        expanded_zh = expander.expand("火车票")
        assert any("railway" in q or "train" in q for q in expanded_zh)

        # English conceptual
        expanded_en = expander.expand("booking")
        assert any("reservation" in q or "ticket" in q for q in expanded_en)

    def test_expand_technical_terms(self) -> None:
        """Test technical term expansion"""
        expander = SynonymExpander()

        expanded = expander.expand("k8s")
        assert any("kubernetes" in q for q in expanded)

        expanded = expander.expand("postgres")
        assert any("postgresql" in q for q in expanded)

    def test_expand_no_match(self) -> None:
        """Test query with no known synonyms"""
        expander = SynonymExpander()
        expanded = expander.expand("unknown term")
        assert expanded == ["unknown term"]

    def test_expand_empty(self) -> None:
        """Test empty query"""
        expander = SynonymExpander()
        expanded = expander.expand("")
        assert expanded == [""]

    def test_expand_limit(self) -> None:
        """Test expansion is limited to 5 variations"""
        expander = SynonymExpander()
        # "api" has multiple synonyms (api, rest, endpoint)
        expanded = expander.expand("api")
        assert len(expanded) <= 5

    def test_expand_no_substring_false_positive(self) -> None:
        """auth/authentication must not match inside authenticate."""
        expander = SynonymExpander()
        expanded = expander.expand("authenticate user")
        assert expanded == ["authenticate user"]
        assert not any("enticate user" in q and q != "authenticate user" for q in expanded)

    def test_expand_whole_word_auth(self) -> None:
        """Whole-word auth should still expand to authentication."""
        expander = SynonymExpander()
        expanded = expander.expand("auth token")
        assert "auth token" in expanded
        assert any("authentication token" in q for q in expanded)

    def test_shipped_config_is_loaded(self) -> None:
        """The packaged synonyms.yaml is the only source; an empty load would silence expansion."""
        expander = SynonymExpander()
        assert len(expander._all_synonyms) > 100
        assert "数据库" in expander._all_synonyms
        assert "database" in expander._all_synonyms

    def test_missing_config_leaves_expander_inert(self, tmp_path) -> None:
        """No built-in copy of the tables: a missing file means no expansion, not stale defaults."""
        expander = SynonymExpander(config_path=tmp_path / "absent.yaml")
        assert expander.expand("database") == ["database"]

    def test_custom_config_path_is_honored(self, tmp_path) -> None:
        config = tmp_path / "synonyms.yaml"
        config.write_text("english:\n  widget: [gadget]\nchinese:\n  部件: [component]\n", encoding="utf-8")

        expander = SynonymExpander(config_path=config)

        assert expander.expand("widget") == ["widget", "gadget"]
        assert expander.expand("部件") == ["部件", "component"]
