"""Unit tests for Bitable & Spreadsheet Sidebar Interactive CoPilot Engine.

Tests schema identification, cell value synthesis, batch wrangling, and REST router.
"""

from __future__ import annotations

import pytest

from app.api.channels.bitable_copilot_router import WrangleRequest, wrangle_table_data
from app.services.bitable_copilot.engine import DataWranglingEngine
from app.services.bitable_copilot.models import (
    TableContextPayload,
    TableFieldSchema,
    TableRowData,
)


@pytest.fixture
def sample_table_context() -> TableContextPayload:
    """Fixture providing a standard table context with multiple fields and rows."""
    fields = [
        TableFieldSchema(field_id="col_feedback", name="用户反馈", field_type="text"),
        TableFieldSchema(field_id="col_sentiment", name="情感倾向", field_type="single_select"),
        TableFieldSchema(field_id="col_tag", name="技术标签", field_type="text"),
    ]
    rows = [
        TableRowData(
            row_id="row_1",
            cells={"col_feedback": "这个新功能太好用了，性能飞快，UI 也很棒！", "col_sentiment": None, "col_tag": None},
        ),
        TableRowData(
            row_id="row_2",
            cells={"col_feedback": "系统报错了，经常卡死，体验很差，有 bug。", "col_sentiment": None, "col_tag": None},
        ),
        TableRowData(
            row_id="row_3",
            cells={"col_feedback": "今天发布了新版本 1.2.0。", "col_sentiment": None, "col_tag": None},
        ),
    ]
    return TableContextPayload(
        table_id="tbl_feedback_001",
        table_name="客户声音分析表",
        fields=fields,
        rows=rows,
    )


def test_identify_target_field_by_name(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    
    # 1. Mention field explicitly in prompt
    target = engine.identify_target_field(
        prompt="请分析每一行的情感倾向并打标",
        fields=sample_table_context.fields,
    )
    assert target.field_id == "col_sentiment"
    assert target.name == "情感倾向"

    # 2. Mention another field
    target_tag = engine.identify_target_field(
        prompt="提取技术标签",
        fields=sample_table_context.fields,
    )
    assert target_tag.field_id == "col_tag"


def test_identify_target_field_by_active_focus(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    
    # When prompt is generic, use active_field_id
    target = engine.identify_target_field(
        prompt="进行深度分析",
        fields=sample_table_context.fields,
        active_field_id="col_tag",
    )
    assert target.field_id == "col_tag"


def test_batch_sentiment_wrangling(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    
    result = engine.process_table_instruction(
        context=sample_table_context,
        instruction="分析情感倾向",
    )
    
    assert result.table_id == "tbl_feedback_001"
    assert result.target_field_id == "col_sentiment"
    assert result.total_processed == 3
    assert result.total_mutated == 3
    assert len(result.mutations) == 3

    # Row 1 -> Positive
    assert result.mutations[0].row_id == "row_1"
    assert "Positive" in str(result.mutations[0].new_value)

    # Row 2 -> Negative
    assert result.mutations[1].row_id == "row_2"
    assert "Negative" in str(result.mutations[1].new_value)

    # Row 3 -> Neutral
    assert result.mutations[2].row_id == "row_3"
    assert "Neutral" in str(result.mutations[2].new_value)


def test_batch_tag_extraction_wrangling(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    
    result = engine.process_table_instruction(
        context=sample_table_context,
        instruction="根据描述提取技术标签",
    )
    
    assert result.target_field_id == "col_tag"
    assert len(result.mutations) == 3
    
    # Row 1 mentions 性能, UI -> Performance, Frontend
    row1_tags = str(result.mutations[0].new_value)
    assert "Performance" in row1_tags or "Frontend" in row1_tags


def test_selected_rows_only_filtering(sample_table_context: TableContextPayload) -> None:
    engine = DataWranglingEngine()
    sample_table_context.selected_row_ids = ["row_1"]
    
    result = engine.process_table_instruction(
        context=sample_table_context,
        instruction="分析情感倾向",
    )
    
    assert result.total_processed == 1
    assert result.total_mutated == 1
    assert len(result.mutations) == 1
    assert result.mutations[0].row_id == "row_1"


@pytest.mark.asyncio
async def test_bitable_copilot_router_endpoint(sample_table_context: TableContextPayload) -> None:
    req = WrangleRequest(
        context=sample_table_context,
        instruction="请将描述分析并归类到情感倾向列",
    )
    
    res = await wrangle_table_data(req=req, _identity=None)
    assert res.table_id == "tbl_feedback_001"
    assert res.target_field_id == "col_sentiment"
    assert res.total_processed == 3
    assert len(res.mutations) == 3
