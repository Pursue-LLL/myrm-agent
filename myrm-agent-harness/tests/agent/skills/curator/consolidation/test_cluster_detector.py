"""The cluster detector groups skills by the prefix their names share."""

from __future__ import annotations

from myrm_agent_harness.agent.skills.curator.consolidation.cluster_detector import ClusterDetector
from tests.support.skill_factory import make_skill


class TestClusterDetector:
    """Tests for ClusterDetector prefix-based detection."""

    def test_detect_groups_skills_by_shared_prefix(self) -> None:
        skills = [
            make_skill("git_commit_skill", "Commit changes to git"),
            make_skill("git_push_skill", "Push changes to remote"),
            make_skill("git_merge_skill", "Merge branches"),
            make_skill("deploy_docker_skill", "Deploy with Docker"),
            make_skill("deploy_k8s_skill", "Deploy to Kubernetes"),
        ]

        clusters = ClusterDetector(min_cluster_size=3).detect(skills)

        assert [c.cluster_id for c in clusters] == ["prefix-git"]
        assert clusters[0].shared_domain == "git"
        assert clusters[0].skill_names == ("git_commit_skill", "git_push_skill", "git_merge_skill")

    def test_detect_ignores_descriptions(self) -> None:
        """Skills with near-identical descriptions but unrelated names are not a family."""
        skills = [make_skill(f"{prefix}_helper", "Format a date for display") for prefix in ("alpha", "beta", "gamma")]

        assert ClusterDetector(min_cluster_size=3).detect(skills) == []

    def test_detect_one_cluster_per_prefix(self) -> None:
        skills = [make_skill(f"{prefix}_{i}") for prefix in ("git", "deploy") for i in range(3)]

        clusters = ClusterDetector(min_cluster_size=3).detect(skills)

        assert sorted(c.cluster_id for c in clusters) == ["prefix-deploy", "prefix-git"]
        assert all(len(c.skill_names) == 3 for c in clusters)

    def test_detect_skips_families_below_minimum_size(self) -> None:
        skills = [make_skill("git_commit"), make_skill("git_push"), make_skill("deploy_docker")]

        assert ClusterDetector(min_cluster_size=3).detect(skills) == []

    def test_detect_skips_prefixes_that_are_too_short(self) -> None:
        skills = [make_skill(f"ai_{suffix}") for suffix in ("chat", "draw", "music")]

        assert ClusterDetector(min_cluster_size=3).detect(skills) == []

    def test_detect_skips_single_word_names(self) -> None:
        skills = [make_skill(name) for name in ("deploy_skill", "build_skill", "release_skill")]

        assert ClusterDetector(min_cluster_size=3).detect(skills) == []

    def test_detect_too_few_skills(self) -> None:
        assert ClusterDetector(min_cluster_size=3).detect([make_skill("only_one_skill")]) == []


class TestClusterDetectorEdgeCases:
    """Edge case tests for ClusterDetector."""

    def test_extract_prefix_single_word(self) -> None:
        prefix = ClusterDetector._extract_prefix("singleword")
        assert prefix == ""

    def test_extract_prefix_multi_word(self) -> None:
        prefix = ClusterDetector._extract_prefix("git-commit-fast")
        assert prefix == "git"
