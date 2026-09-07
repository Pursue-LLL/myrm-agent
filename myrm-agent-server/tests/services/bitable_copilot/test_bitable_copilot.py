"""Unit tests for Bitable & Spreadsheet Sidebar Interactive CoPilot Data Wrangling Engine."""

from __future__ import annotations

import pytest

from app.services.bitable_copilot.engine import DataWranglingEngine
from app.services.bitable_copilot.models import (
    TableContextPayload,
    TableFieldSchema,
    TableRowData,
)


@pytest.fixture
def sample_table_context() -> TableContextPayload:
    fields = [
        TableFieldSchema(field_id="fld_name", name="Customer Feedback", field_type="text"),
        TableFieldSchema(field_id="fld_sentiment", name="Sentiment Tag", field_type="single_select"),
        TableFieldSchema(field_id="fld_tags", name="Topics", field_type="multi_select"),
    ]
    rows = [
        TableRowData(row_id="rec_1", cells={"fld_name": "这个系统响应速度太快了，体验非常棒！", "fld_sentiment": None}),
        TableRowData(row_id="rec_2", cells={"fld_name": "最近经常报 bug，登录也很慢", "fld_sentiment": None}),
        TableRowData(row_id="rec_3", cells={"fld_name": "界面排版还行，功能基本正常", "fld_sentiment": None}),
    ]
    return TableContextPayload(
        table_id="tbl_feedback_2026",
        table_name="用户反馈看板",
        fields=fields,
        rows=rows,
        active_field_id="fld_sentiment",
    )


def test_identify_target_field_explicit_and_focused(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    
    # Explicit mention in instruction
    target = engine.identify_target_field("请帮我提取 Topics 标签", sample_table_context.fields)
    assert target.field_id == "fld_tags"

    # Fallback to active focused field
    target_active = engine.identify_target_field("分析这几行文本", sample_table_context.fields, active_field_id="fld_sentiment")
    assert target_active.field_id == "fld_sentiment"


def test_sentiment_analysis_wrangling_batch(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    result = engine.process_table_instruction(sample_table_context, "对客户反馈做情感分类")

    assert result.target_field_id == "fld_sentiment"
    assert result.total_processed == 3
    assert result.total_mutated == 3
    assert len(result.mutations) == 3

    # Verify classification logic
    mut_map = {m.row_id: m.new_value for m in result.mutations}
    assert "正面" in mut_map["rec_1"]
    assert "负面" in mut_map["rec_2"]
    assert "中性" in mut_map["rec_3"]


def test_custom_mock_ai_processor(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()

    def mock_processor(row_cells: dict[str, object], instruction: str, target_field: TableFieldSchema) -> tuple[str, str]:
        source = str(row_cells.get("fld_name", ""))
        return f"AI[{len(source)}字]", "Custom character count generator"

    result = engine.process_table_instruction(
        sample_table_context,
        "提取字符数到 Topics 字段",
        mock_ai_processor=mock_processor,
    )

    assert result.target_field_id == "fld_tags"
    assert result.total_mutated == 3
    for mutation in result.mutations:
        assert mutation.new_value.startswith("AI[")
        assert mutation.reasoning == "Custom character count generator"
