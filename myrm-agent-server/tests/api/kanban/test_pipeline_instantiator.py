"""Unit tests for pipeline template instantiator.

Tests cover:
- Pipeline skill discovery (list_pipeline_skills)
- Single pipeline retrieval (get_pipeline_skill)
- String template substitution (_substitute_template)
- Role-to-agent matching (_match_role_to_agent)
- PipelineSpec parsing (_parse_pipeline_spec)
- repeat_for fan-out (_split_repeat_items, TaskSeed.repeat_for parsing)
- Fan-out pipeline templates (multi-topic-research / content-distribution / competitive-analysis)
"""

from __future__ import annotations

from app.services.kanban.pipeline_instantiator import (
    RoleTemplate,
    _match_role_to_agent,
    _parse_pipeline_spec,
    _split_repeat_items,
    _substitute_template,
    get_pipeline_skill,
    list_pipeline_skills,
)


class TestSubstituteTemplate:
    """Deterministic string template substitution."""

    def test_basic_substitution(self) -> None:
        result = _substitute_template("调研：{video_type}领域素材", {"video_type": "产品宣传"})
        assert result == "调研：产品宣传领域素材"

    def test_multiple_placeholders(self) -> None:
        template = "为{topic}撰写{duration}的{video_type}脚本"
        answers = {"topic": "AI产品", "duration": "30s", "video_type": "教程"}
        result = _substitute_template(template, answers)
        assert result == "为AI产品撰写30s的教程脚本"

    def test_missing_key_preserved(self) -> None:
        result = _substitute_template("调研：{video_type}领域{missing}", {"video_type": "教程"})
        assert result == "调研：教程领域{missing}"

    def test_empty_answers(self) -> None:
        result = _substitute_template("调研：{video_type}领域", {})
        assert result == "调研：{video_type}领域"

    def test_no_placeholders(self) -> None:
        result = _substitute_template("审查与交付", {"video_type": "教程"})
        assert result == "审查与交付"

    def test_empty_template(self) -> None:
        result = _substitute_template("", {"key": "val"})
        assert result == ""


class TestMatchRoleToAgent:
    """Role-to-agent matching by skill overlap."""

    def test_no_agents_returns_default(self) -> None:
        role = RoleTemplate(role_id="writer", description="写作", required_skills=["creative-ideation"])
        result = _match_role_to_agent(role, [], "default-agent")
        assert result == "default-agent"

    def test_exact_skill_match(self) -> None:
        role = RoleTemplate(role_id="researcher", description="研究", required_skills=["deep-research", "web-scraping"])
        agents = [
            {"id": "agent-1", "skill_ids": ["deep-research", "web-scraping", "data-analysis"]},
            {"id": "agent-2", "skill_ids": ["creative-ideation"]},
        ]
        result = _match_role_to_agent(role, agents, "default")
        assert result == "agent-1"

    def test_partial_match_picks_best(self) -> None:
        role = RoleTemplate(role_id="analyst", description="分析", required_skills=["data-analysis", "web-scraping"])
        agents = [
            {"id": "agent-1", "skill_ids": ["data-analysis"]},
            {"id": "agent-2", "skill_ids": ["data-analysis", "web-scraping"]},
        ]
        result = _match_role_to_agent(role, agents, "default")
        assert result == "agent-2"

    def test_no_overlap_returns_default(self) -> None:
        role = RoleTemplate(role_id="reviewer", description="审核", required_skills=["code-review"])
        agents = [
            {"id": "agent-1", "skill_ids": ["creative-ideation"]},
        ]
        result = _match_role_to_agent(role, agents, "fallback")
        assert result == "fallback"


class TestParsePipelineSpec:
    """Parse pipeline_spec from frontmatter dict."""

    def test_minimal_spec(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "test-pipeline",
            "description": "A test pipeline",
            "category": "pipeline",
            "tags": ["pipeline", "test"],
            "pipeline_spec": {
                "discovery_questions": [
                    {
                        "group": "basic",
                        "group_label": "基础",
                        "questions": [
                            {"id": "q1", "type": "text", "label": "问题1"},
                        ],
                    },
                ],
                "role_templates": [
                    {"role_id": "worker", "description": "工作者", "required_skills": ["skill-a"]},
                ],
                "task_graph_seed": [
                    {"title_template": "任务 {q1}", "description_template": "执行 {q1}", "role": "worker", "parents": []},
                ],
                "task_graph_variants": [
                    {
                        "id": "quick",
                        "label": "Quick Mode",
                        "description": "Fast execution",
                        "seeds": [
                            {"title_template": "Quick {q1}", "description_template": "Fast {q1}", "role": "worker", "parents": []},
                        ],
                    }
                ],
            },
        }
        spec = _parse_pipeline_spec("test-pipeline", frontmatter)
        assert spec is not None
        assert spec.skill_id == "test-pipeline"
        assert spec.name == "test-pipeline"
        assert len(spec.discovery_questions) == 1
        assert len(spec.discovery_questions[0].questions) == 1
        assert spec.discovery_questions[0].questions[0].id == "q1"
        assert len(spec.role_templates) == 1
        assert spec.role_templates[0].role_id == "worker"
        assert len(spec.task_graph_seed) == 1
        assert spec.task_graph_seed[0].parents == []
        assert len(spec.task_graph_variants) == 1
        assert spec.task_graph_variants[0].id == "quick"
        assert len(spec.task_graph_variants[0].seeds) == 1
        assert spec.task_graph_variants[0].seeds[0].title_template == "Quick {q1}"

    def test_no_pipeline_spec_returns_none(self) -> None:
        frontmatter: dict[str, object] = {"name": "normal-skill", "description": "Not a pipeline"}
        spec = _parse_pipeline_spec("normal-skill", frontmatter)
        assert spec is None

    def test_pipeline_spec_with_parents(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "dag-test",
            "description": "DAG test",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [],
                "role_templates": [],
                "task_graph_seed": [
                    {"title_template": "T0", "description_template": "D0", "role": "a", "parents": []},
                    {"title_template": "T1", "description_template": "D1", "role": "b", "parents": [0]},
                    {"title_template": "T2", "description_template": "D2", "role": "c", "parents": [0, 1]},
                ],
            },
        }
        spec = _parse_pipeline_spec("dag-test", frontmatter)
        assert spec is not None
        assert spec.task_graph_seed[0].parents == []
        assert spec.task_graph_seed[1].parents == [0]
        assert spec.task_graph_seed[2].parents == [0, 1]

    def test_multi_select_question(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "multi",
            "description": "Multi-select",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [
                    {
                        "group": "focus",
                        "group_label": "重点",
                        "questions": [
                            {"id": "focus", "type": "multi-select", "label": "重点", "options": ["A", "B", "C"]},
                        ],
                    },
                ],
                "role_templates": [],
                "task_graph_seed": [],
            },
        }
        spec = _parse_pipeline_spec("multi", frontmatter)
        assert spec is not None
        q = spec.discovery_questions[0].questions[0]
        assert q.type == "multi-select"
        assert q.options == ["A", "B", "C"]


class TestListPipelineSkills:
    """Discover pipeline skills from assets directory."""

    def test_discovers_pipeline_skills(self) -> None:
        specs = list_pipeline_skills()
        assert len(specs) >= 3
        skill_ids = [s.skill_id for s in specs]
        assert "video-production-pipeline" in skill_ids
        assert "code-review-pipeline" in skill_ids
        assert "data-analysis-pipeline" in skill_ids

    def test_excludes_non_pipeline_skills(self) -> None:
        specs = list_pipeline_skills()
        skill_ids = [s.skill_id for s in specs]
        assert "data-analysis" not in skill_ids
        assert "code-review" not in skill_ids
        assert "multi-agent-orchestration" not in skill_ids

    def test_pipeline_specs_have_task_seeds(self) -> None:
        specs = list_pipeline_skills()
        for spec in specs:
            assert len(spec.task_graph_seed) > 0, f"{spec.skill_id} has no task seeds"
            assert len(spec.role_templates) > 0, f"{spec.skill_id} has no roles"


class TestGetPipelineSkill:
    """Get a specific pipeline skill by ID."""

    def test_existing_skill(self) -> None:
        spec = get_pipeline_skill("video-production-pipeline")
        assert spec is not None
        assert spec.skill_id == "video-production-pipeline"
        assert spec.category == "pipeline"
        assert len(spec.task_graph_seed) == 5
        assert len(spec.role_templates) == 5
        assert len(spec.discovery_questions) == 2

    def test_non_existent_skill(self) -> None:
        spec = get_pipeline_skill("non-existent-pipeline")
        assert spec is None

    def test_non_pipeline_skill_returns_none(self) -> None:
        spec = get_pipeline_skill("data-analysis")
        assert spec is None

    def test_video_pipeline_dag_structure(self) -> None:
        spec = get_pipeline_skill("video-production-pipeline")
        assert spec is not None
        seeds = spec.task_graph_seed
        assert seeds[0].parents == []
        assert seeds[1].parents == []
        assert seeds[2].parents == [0]
        assert seeds[3].parents == [1, 2]
        assert seeds[4].parents == [3]

    def test_code_review_pipeline_roles(self) -> None:
        spec = get_pipeline_skill("code-review-pipeline")
        assert spec is not None
        role_ids = [r.role_id for r in spec.role_templates]
        assert "analyzer" in role_ids
        assert "security_reviewer" in role_ids
        assert "logic_reviewer" in role_ids
        assert "verifier" in role_ids


class TestEdgeCases:
    """Edge cases and robustness tests."""

    def test_substitute_special_chars_in_answer(self) -> None:
        result = _substitute_template("标题：{topic}", {"topic": "C++ {templates} & std::vector"})
        assert "C++ {templates} & std::vector" in result

    def test_substitute_curly_braces_in_template(self) -> None:
        result = _substitute_template("代码 {{literal}} 和 {topic}", {"topic": "Python"})
        assert "Python" in result

    def test_match_role_skills_field_alternative(self) -> None:
        role = RoleTemplate(role_id="coder", description="编码", required_skills=["code-exec"])
        agents = [{"id": "a1", "skills": ["code-exec", "debug"]}]
        result = _match_role_to_agent(role, agents, None)
        assert result == "a1"

    def test_match_role_default_none(self) -> None:
        role = RoleTemplate(role_id="x", description="", required_skills=["unknown"])
        result = _match_role_to_agent(role, [], None)
        assert result is None

    def test_parse_spec_with_invalid_parent_types(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "test",
            "description": "t",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [],
                "role_templates": [],
                "task_graph_seed": [
                    {"title_template": "T0", "description_template": "D0", "role": "a", "parents": ["invalid", None, 1.5]},
                ],
            },
        }
        spec = _parse_pipeline_spec("test", frontmatter)
        assert spec is not None
        assert spec.task_graph_seed[0].parents == [1]

    def test_parse_spec_empty_questions_group(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "empty-q",
            "description": "t",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [{"group": "g", "group_label": "G", "questions": []}],
                "role_templates": [],
                "task_graph_seed": [
                    {"title_template": "T0", "description_template": "D0", "role": "a", "parents": []},
                ],
            },
        }
        spec = _parse_pipeline_spec("empty-q", frontmatter)
        assert spec is not None
        assert spec.discovery_questions[0].questions == []

    def test_parse_spec_with_invalid_variant_types(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "test",
            "description": "t",
            "category": "pipeline",
            "pipeline_spec": {
                "task_graph_variants": [
                    "invalid",
                    {
                        "id": "v1",
                        "seeds": ["invalid", {"title_template": "T0", "role": "a", "parents": []}],
                    },
                ],
            },
        }
        spec = _parse_pipeline_spec("test", frontmatter)
        assert spec is not None
        assert len(spec.task_graph_variants) == 1
        assert len(spec.task_graph_variants[0].seeds) == 1
        assert spec.task_graph_variants[0].seeds[0].title_template == "T0"

    def test_load_frontmatter_nonexistent(self) -> None:
        from pathlib import Path

        from app.services.kanban.pipeline_instantiator import _load_frontmatter

        result = _load_frontmatter(Path("/nonexistent/path/SKILL.md"))
        assert result is None

    def test_all_pipelines_valid_dag(self) -> None:
        """Verify all pipeline DAGs have valid parent indices."""
        specs = list_pipeline_skills()
        for spec in specs:
            for i, seed in enumerate(spec.task_graph_seed):
                for p in seed.parents:
                    assert 0 <= p < i, f"{spec.skill_id}: task[{i}] references parent[{p}] >= self index"


class TestRepeatFor:
    """repeat_for fan-out: a single seed expands into N parallel tasks."""

    def test_split_repeat_items_basic(self) -> None:
        assert _split_repeat_items("AI,Quantum,Bio") == ["AI", "Quantum", "Bio"]

    def test_split_repeat_items_with_whitespace(self) -> None:
        assert _split_repeat_items(" AI , Quantum , Bio ") == ["AI", "Quantum", "Bio"]

    def test_split_repeat_items_empty(self) -> None:
        assert _split_repeat_items("") == []

    def test_split_repeat_items_trailing_comma(self) -> None:
        assert _split_repeat_items("AI,Quantum,") == ["AI", "Quantum"]

    def test_split_repeat_items_single(self) -> None:
        assert _split_repeat_items("AI") == ["AI"]

    def test_parse_repeat_for_field(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "fanout-test",
            "description": "test",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [],
                "role_templates": [],
                "task_graph_seed": [
                    {
                        "title_template": "Research: {_item}",
                        "description_template": "Investigate {_item}",
                        "role": "researcher",
                        "parents": [],
                        "repeat_for": "topics",
                    },
                    {
                        "title_template": "Synthesize",
                        "description_template": "Combine all findings",
                        "role": "synthesizer",
                        "parents": [0],
                    },
                ],
            },
        }
        spec = _parse_pipeline_spec("fanout-test", frontmatter)
        assert spec is not None
        assert spec.task_graph_seed[0].repeat_for == "topics"
        assert spec.task_graph_seed[1].repeat_for is None

    def test_parse_repeat_for_absent(self) -> None:
        frontmatter: dict[str, object] = {
            "name": "no-repeat",
            "description": "test",
            "category": "pipeline",
            "pipeline_spec": {
                "discovery_questions": [],
                "role_templates": [],
                "task_graph_seed": [
                    {"title_template": "T0", "description_template": "D0", "role": "a", "parents": []},
                ],
            },
        }
        spec = _parse_pipeline_spec("no-repeat", frontmatter)
        assert spec is not None
        assert spec.task_graph_seed[0].repeat_for is None

    def test_substitute_item_placeholder(self) -> None:
        result = _substitute_template("Research: {_item}", {"_item": "Quantum Computing", "depth": "deep"})
        assert result == "Research: Quantum Computing"


class TestFanOutTemplates:
    """Verify the 3 new fan-out pipeline templates load correctly."""

    def test_multi_topic_research_pipeline(self) -> None:
        spec = get_pipeline_skill("multi-topic-research-pipeline")
        assert spec is not None
        assert spec.category == "pipeline"
        assert len(spec.task_graph_seed) == 2
        assert spec.task_graph_seed[0].repeat_for == "topics"
        assert spec.task_graph_seed[1].repeat_for is None
        assert spec.task_graph_seed[1].parents == [0]

    def test_content_distribution_pipeline(self) -> None:
        spec = get_pipeline_skill("content-distribution-pipeline")
        assert spec is not None
        assert spec.category == "pipeline"
        assert len(spec.task_graph_seed) == 2
        assert spec.task_graph_seed[0].repeat_for == "platforms"
        assert spec.task_graph_seed[1].repeat_for is None
        assert spec.task_graph_seed[1].parents == [0]

    def test_competitive_analysis_pipeline(self) -> None:
        spec = get_pipeline_skill("competitive-analysis-pipeline")
        assert spec is not None
        assert spec.category == "pipeline"
        assert len(spec.task_graph_seed) == 2
        assert spec.task_graph_seed[0].repeat_for == "competitors"
        assert spec.task_graph_seed[1].repeat_for is None
        assert spec.task_graph_seed[1].parents == [0]

    def test_fan_out_templates_in_discovery(self) -> None:
        specs = list_pipeline_skills()
        skill_ids = [s.skill_id for s in specs]
        assert "multi-topic-research-pipeline" in skill_ids
        assert "content-distribution-pipeline" in skill_ids
        assert "competitive-analysis-pipeline" in skill_ids

    def test_fan_out_dags_valid(self) -> None:
        for sid in ("multi-topic-research-pipeline", "content-distribution-pipeline", "competitive-analysis-pipeline"):
            spec = get_pipeline_skill(sid)
            assert spec is not None
            for i, seed in enumerate(spec.task_graph_seed):
                for p in seed.parents:
                    assert 0 <= p < i, f"{sid}: task[{i}] references parent[{p}] >= self index"
