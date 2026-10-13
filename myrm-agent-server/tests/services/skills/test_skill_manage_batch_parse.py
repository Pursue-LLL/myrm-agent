"""skill_manage_batch_parse extracts batch_id for progress enrichment."""

from app.services.skills.skill_manage_batch_parse import extract_skill_mutation_batch_id_from_step


def test_extract_batch_id_from_successful_skill_manage_step() -> None:
    batch_id = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
    step = {
        "tool_name": "skill_manage_tool",
        "status": "success",
        "items": [
            {
                "text": f"Batch applied successfully (batch_id={batch_id}, operations=1).\n\nSaved.",
            }
        ],
    }
    assert extract_skill_mutation_batch_id_from_step(step) == batch_id


def test_extract_batch_id_from_structured_json_footer() -> None:
    batch_id = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
    step = {
        "tool_name": "skill_manage_tool",
        "status": "success",
        "items": [
            {
                "text": (
                    "Batch applied successfully (batch_id=ignored, operations=1).\n\n"
                    f"myrm_skill_batch:{{\"batch_id\":\"{batch_id}\"}}"
                ),
            }
        ],
    }
    assert extract_skill_mutation_batch_id_from_step(step) == batch_id


def test_ignores_failed_skill_manage_step() -> None:
    step = {
        "tool_name": "skill_manage_tool",
        "status": "error",
        "items": [{"text": "Batch applied successfully (batch_id=abc)."}],
    }
    assert extract_skill_mutation_batch_id_from_step(step) is None
