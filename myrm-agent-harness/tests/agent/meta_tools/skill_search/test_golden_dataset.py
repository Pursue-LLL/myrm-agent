"""Tests for Golden Dataset evaluation

This test file demonstrates how to use the Golden Dataset to evaluate
search quality. It's designed to be run manually or as part of CI/CD
to track search quality over time.
"""

import pytest

from myrm_agent_harness.backends.skills.types import SkillMetadata

from .fixtures import create_comprehensive_mock_skills
from .golden_dataset import GOLDEN_DATASET, evaluate_search_quality, print_evaluation_report


@pytest.fixture
def mock_skills() -> list[SkillMetadata]:
    """Create comprehensive mock skills for testing"""
    return create_comprehensive_mock_skills()


def test_golden_dataset_structure():
    """Test that golden dataset has valid structure"""
    assert len(GOLDEN_DATASET) > 0, "Golden dataset should not be empty"

    for query in GOLDEN_DATASET:
        assert query.query, "Query should not be empty"
        assert query.expected_skills, "Expected skills should not be empty"
        assert query.description, "Description should not be empty"
        assert query.category, "Category should not be empty"


def test_golden_dataset_categories():
    """Test that golden dataset covers all important categories"""
    categories = {q.category for q in GOLDEN_DATASET}

    expected_categories = {
        "exact_match",
        "semantic_chinese",
        "semantic_english",
        "multilingual",
        "multilingual_format",
        "conceptual",
        "synonym",
        "short_query",
        "long_query",
        "fuzzy",
        "error_query",
    }

    assert categories == expected_categories, f"Missing categories: {expected_categories - categories}"


def test_golden_dataset_size():
    """Test that golden dataset has sufficient size for statistical significance"""
    assert len(GOLDEN_DATASET) >= 100, f"Golden dataset should have at least 100 queries, got {len(GOLDEN_DATASET)}"

    category_counts = {}
    for query in GOLDEN_DATASET:
        category_counts[query.category] = category_counts.get(query.category, 0) + 1

    for category, count in category_counts.items():
        assert count >= 5, f"Category '{category}' should have at least 5 queries, got {count}"


# Measured on the 145-query dataset: MRR 0.839, top-1 0.738, top-3 0.938, top-5 0.966. Each floor sits a few points
# below, so ordinary tuning passes while a broken tokenizer, scorer or synonym table does not.
_MIN_MRR = 0.80
_MIN_TOP1 = 0.70
_MIN_TOP3 = 0.90
_MIN_TOP5 = 0.94


def test_evaluate_search_quality_bm25(mock_skills):
    """The lexical engine keeps its measured quality on the golden dataset."""
    from myrm_agent_harness.agent.meta_tools.skills.search.engine import SkillSearchEngine

    engine = SkillSearchEngine(mock_skills)

    def search_func(query: str):
        return engine.search_bm25(query, top_k=5)

    results = evaluate_search_quality(search_func, GOLDEN_DATASET)

    print_evaluation_report(results)

    assert results["total_queries"] == len(GOLDEN_DATASET)
    assert results["mrr"] >= _MIN_MRR
    assert results["top1_accuracy"] >= _MIN_TOP1
    assert results["top3_accuracy"] >= _MIN_TOP3
    assert results["top5_accuracy"] >= _MIN_TOP5


def test_evaluation_metrics_calculation():
    """Test that evaluation metrics are calculated correctly"""

    def mock_search_func(query: str):
        if query == "exact":
            return [
                type("Result", (), {"name": "expected_skill_1"}),
                type("Result", (), {"name": "other_skill"}),
            ]
        if query == "top3":
            return [
                type("Result", (), {"name": "other_skill_1"}),
                type("Result", (), {"name": "other_skill_2"}),
                type("Result", (), {"name": "expected_skill_2"}),
            ]
        return []

    dataset = [
        type(
            "Query",
            (),
            {
                "query": "exact",
                "expected_skills": ["expected_skill_1"],
                "description": "Test",
                "category": "test",
            },
        ),
        type(
            "Query",
            (),
            {
                "query": "top3",
                "expected_skills": ["expected_skill_2"],
                "description": "Test",
                "category": "test",
            },
        ),
        type(
            "Query",
            (),
            {
                "query": "miss",
                "expected_skills": ["expected_skill_3"],
                "description": "Test",
                "category": "test",
            },
        ),
    ]

    results = evaluate_search_quality(mock_search_func, dataset)

    assert results["total_queries"] == 3
    assert results["top1_accuracy"] == pytest.approx(1 / 3)
    assert results["top3_accuracy"] == pytest.approx(2 / 3)
    assert results["mrr"] == pytest.approx((1.0 + 1 / 3 + 0.0) / 3)
