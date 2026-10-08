"""Service provider for Life Milestones and Personal Timeline Suite.

[POS]
Maintains the singleton LifeMilestonesSuite instance for the server,
pre-populating seed milestones and evolving philosophies.

[INPUT]
- myrm_agent_harness.toolkits.memory

[OUTPUT]
- get_life_milestones_suite, reset_life_milestones_suite
"""

from __future__ import annotations

from datetime import datetime, timezone

from myrm_agent_harness.toolkits.memory import (
    GrowthDiaryEntry,
    LifeMilestone,
    LifeMilestonesSuite,
    LifeStageEra,
    MilestoneCategory,
    PrivacyIntimacyLevel,
    ValueSystemNode,
)

_SUITE_INSTANCE: LifeMilestonesSuite | None = None


def _create_prepopulated_suite() -> LifeMilestonesSuite:
    """Instantiate suite populated with initial life milestones and value trajectory."""
    suite = LifeMilestonesSuite()

    # 1. Seed Eras
    suite.register_era(
        LifeStageEra(
            era_id="era_university",
            label="大学探索期",
            start_year=2014,
            end_year=2018,
            guiding_philosophy="沉潜求学，探索计算机科学与纯粹技术之美",
        )
    )
    suite.register_era(
        LifeStageEra(
            era_id="era_growth_startup",
            label="独立奋斗与创业期",
            start_year=2019,
            end_year=2023,
            guiding_philosophy="直面风险，追求在未知中开拓自我边界",
        )
    )
    suite.register_era(
        LifeStageEra(
            era_id="era_family_maturity",
            label="成家立业与长期主义期",
            start_year=2024,
            end_year=None,
            guiding_philosophy="身心健康与温情陪伴为基石，行稳致远高质量创造",
        )
    )

    # 2. Seed Milestones
    suite.record_milestone(
        LifeMilestone(
            milestone_id="ms_seed_grad_2018",
            timestamp_str="2018-06-25",
            year=2018,
            category=MilestoneCategory.EDUCATION,
            title="大学学成毕业",
            narrative="顺利取得计算机科学学士学位，背起行囊迈入行业前沿",
            long_term_impact="开启职业生涯与经济独立长跑",
            core_values=["独立", "求真"],
            significance_score=0.90,
            location="北京",
        )
    )

    suite.record_milestone(
        LifeMilestone(
            milestone_id="ms_seed_relocate_2020",
            timestamp_str="2020-04-10",
            year=2020,
            category=MilestoneCategory.RELOCATION,
            title="移居上海并联合创办工作室",
            narrative="经历了深度思考，决定迁居上海，开启自主产品研发探索",
            long_term_impact="重塑了事业重心与长跑基地",
            core_values=["勇气", "开拓"],
            significance_score=0.92,
            location="上海",
        )
    )

    suite.record_milestone(
        LifeMilestone(
            milestone_id="ms_seed_marriage_2023",
            timestamp_str="2023-10-18",
            year=2023,
            category=MilestoneCategory.FAMILY_LIFE,
            title="与相伴多年的伴侣步入婚姻",
            narrative="在亲友见证下缔结婚约，共同构筑温暖的家庭港湾",
            long_term_impact="人生重心由单一事业延展至家庭幸福与责任",
            core_values=["家庭", "温情", "承诺"],
            intimacy_level=PrivacyIntimacyLevel.INTIMATE_PERSONAL,
            significance_score=0.96,
            location="上海",
        )
    )

    # 3. Seed Value System Evolution
    suite.register_value(
        ValueSystemNode(
            value_id="val_seed_balance",
            theme="工作与生活节律",
            current_stance="深度专注与身心充电并重，追求可持续的高质量长期创造",
            prior_belief="年轻应当竭尽全力追求速度，甚至牺牲作息与健康",
            transition_catalyst="经历初创期的健康警示与成家后的心境转变，领悟长跑重在节律而非透支",
            trigger_milestone_ids=["ms_seed_marriage_2023"],
            effective_since_year=2023,
            is_active=True,
            weight=1.5,
        )
    )

    # 4. Seed Growth Reflection Diary
    suite.record_diary(
        GrowthDiaryEntry(
            entry_id="diary_seed_01",
            timestamp=datetime(2023, 11, 1, 21, 30, tzinfo=timezone.utc),
            emotional_state="笃定安宁",
            reflection_text="夜深人静时整理书架，回看几年前初来上海时的笔记，庆幸自己没有在浮躁的洪流中迷失，慢慢学会了享受慢下来的从容。",
            linked_milestone_id="ms_seed_marriage_2023",
            era_label="成家立业与长期主义期",
        )
    )

    return suite


def get_life_milestones_suite() -> LifeMilestonesSuite:
    """Retrieve the singleton LifeMilestonesSuite instance."""
    global _SUITE_INSTANCE
    if _SUITE_INSTANCE is None:
        _SUITE_INSTANCE = _create_prepopulated_suite()
    return _SUITE_INSTANCE


def reset_life_milestones_suite() -> LifeMilestonesSuite:
    """Reset the singleton instance (primarily for isolated test fixtures)."""
    global _SUITE_INSTANCE
    _SUITE_INSTANCE = _create_prepopulated_suite()
    return _SUITE_INSTANCE
