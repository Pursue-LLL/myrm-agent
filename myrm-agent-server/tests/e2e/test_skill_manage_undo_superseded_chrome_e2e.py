"""Chrome E2E: undoing a skill change while a newer change still holds the skill is refused, said once, and loses nothing."""

from __future__ import annotations

import re

import pytest

from tests.e2e.test_skill_manage_undo_consumed_chrome_e2e import Refusal, check_refused_undo_reaches_the_user
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md, _seed_mutation_batch
from tests.support.chrome_mcp_e2e import get_e2e_api_url, get_e2e_ui_url, http_json

_SUPERSEDED = Refusal(
    localized=re.compile(r"changed again afterwards|之后又被修改过"),
    # The server's own sentence for the 409; the user must only ever see the localized one.
    server_sentence="was changed again by batch",
)


def _undo(api_url: str, batch_id: str) -> None:
    undone = http_json("POST", f"{api_url}/api/v1/skill-optimization/mutations/{batch_id}/rollback")
    assert isinstance(undone, dict) and undone.get("status") == "rolled_back", undone


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_undo_of_an_older_change_while_a_newer_one_holds_the_skill_says_so_once_and_loses_nothing() -> None:
    """Two batches changed the same skill: pressing the older one's Undo is refused with the real 409, the skill stays."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    older = _seed_mutation_batch(api_url)
    newer = _seed_mutation_batch(api_url)
    skill_id, marker_v1, marker_v2 = older["skill_id"], older["marker_v1"], older["marker_v2"]
    assert newer["skill_id"] == skill_id, "the two seeded batches must change the same skill"
    assert marker_v2 in _fetch_skill_md(api_url, skill_id), "the seeded skill does not hold the newest content"

    check_refused_undo_reaches_the_user(api_url, ui_url, older["batch_id"], _SUPERSEDED)

    content = _fetch_skill_md(api_url, skill_id)
    assert marker_v2 in content and marker_v1 not in content, "a refused undo rewrote the skill"

    # The refusal consumed nothing: newest first, both undos still go through.
    _undo(api_url, newer["batch_id"])
    _undo(api_url, older["batch_id"])
    restored = _fetch_skill_md(api_url, skill_id)
    assert marker_v1 in restored and marker_v2 not in restored, "undoing newest first did not restore the skill"
