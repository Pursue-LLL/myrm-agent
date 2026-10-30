"""Tests for TypoCorrector"""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.skills.search.typo_corrector import TypoCorrector


class TestTypoCorrector:
    """Test TypoCorrector functionality"""

    def test_correct_database_typos(self) -> None:
        """Test database-related typo corrections"""
        corrector = TypoCorrector()
        assert corrector.correct("databse") == "database"
        assert corrector.correct("databas") == "database"
        assert corrector.correct("postgre") == "postgres"
        assert corrector.correct("postgress") == "postgres"

    def test_correct_tech_terms(self) -> None:
        """Test technical term typo corrections"""
        corrector = TypoCorrector()
        assert corrector.correct("kubernets") == "kubernetes"
        assert corrector.correct("kubernete") == "kubernetes"
        assert corrector.correct("javascirpt") == "javascript"
        assert corrector.correct("pytohn") == "python"
        assert corrector.correct("dock") == "docker"

    def test_correct_auth_typos(self) -> None:
        """Test authentication typo corrections"""
        corrector = TypoCorrector()
        assert "authentication" in corrector.correct("authentification")
        assert "authentication" in corrector.correct("authentcation")
        assert "authentication" in corrector.correct("autentication")

    def test_correct_chinese_pinyin(self) -> None:
        """Test pinyin to Chinese corrections"""
        corrector = TypoCorrector()
        assert corrector.correct("piao") == "票"
        assert corrector.correct("tianqi") == "天气"

    def test_correct_no_typo(self) -> None:
        """Test that correct words are unchanged"""
        corrector = TypoCorrector()
        assert corrector.correct("database") == "database"
        assert corrector.correct("kubernetes") == "kubernetes"
        assert corrector.correct("python") == "python"

    def test_correct_empty(self) -> None:
        """Test empty query"""
        corrector = TypoCorrector()
        assert corrector.correct("") == ""

    def test_correct_multi_word(self) -> None:
        """Test multi-word query with typos"""
        corrector = TypoCorrector()
        assert corrector.correct("databse query") == "database query"
        assert corrector.correct("postgress backup") == "postgres backup"

    def test_correct_ignores_case(self) -> None:
        """Queries reach the corrector as typed, so lookup must not depend on case."""
        corrector = TypoCorrector()
        assert corrector.correct("Kubernets") == "kubernetes"
        assert corrector.correct("POSTGRESS backup") == "postgres backup"

    def test_correct_keeps_untouched_query_verbatim(self) -> None:
        """Without a typo the original text, punctuation included, is returned as is."""
        corrector = TypoCorrector()
        assert corrector.correct("k8s-deployment v1.2") == "k8s-deployment v1.2"

    def test_shipped_config_is_loaded(self) -> None:
        assert len(TypoCorrector()._corrections) > 10

    def test_missing_config_leaves_corrector_inert(self, tmp_path) -> None:
        corrector = TypoCorrector(config_path=tmp_path / "absent.yaml")
        assert corrector.correct("databse") == "databse"
