from __future__ import annotations

import io
import uuid
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.packaging import serialize_eval_cases

from app.api.skills.batch_import import router
from app.api.skills.evolution.helpers import _get_skill_store
from app.core.skills.store.evolution_store import reset_evolution_skill_store


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    return TestClient(app)


def _build_zip_with_skill(
    skill_dir: str, *, name: str, description: str, content: str
) -> bytes:
    buffer = io.BytesIO()
    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n{content}\n"
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{skill_dir}/SKILL.md", skill_md)
    return buffer.getvalue()


def _build_zip_without_skill_md(skill_dir: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{skill_dir}/README.txt", "not a skill")
    return buffer.getvalue()


def _build_zip_with_evals(
    skill_dir: str, *, name: str, description: str, content: str
) -> bytes:
    buffer = io.BytesIO()
    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n{content}\n"
    eval_cases = [
        {
            "message": "sum 1 and 2",
            "expected_tools": ["code_interpreter"],
            "require_all": True,
        }
    ]
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{skill_dir}/SKILL.md", skill_md)
        archive.writestr(
            f"{skill_dir}/evals.json", serialize_eval_cases(name, eval_cases)
        )
    return buffer.getvalue()


def _preview_batch_import(client: TestClient, zip_bytes: bytes) -> dict:
    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    return response.json()


def _confirm_batch_import(
    client: TestClient, session_id: str, items: list[dict]
) -> dict:
    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={"session_id": session_id, "items": items},
    )
    assert response.status_code == 200
    return response.json()


def test_batch_import_preview_returns_empty_payload_when_zip_contains_no_skill_md() -> (
    None
):
    client = _make_client()
    zip_bytes = _build_zip_without_skill_md("no-skill")

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "",
        "items": [],
        "total_found": 0,
        "total_conflicts": 0,
    }


def test_batch_import_confirm_missing_session_returns_structured_detail() -> None:
    client = _make_client()
    missing_session = f"missing-{uuid.uuid4().hex}"

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": missing_session,
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "missing-session-skill",
                    "description": "desc",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert set(detail.keys()) == {"message", "error_code"}
    assert detail["error_code"] == ""
    assert "Session" in detail["message"]


def test_batch_import_preview_then_confirm_succeeds_on_real_zip_flow() -> None:
    client = _make_client()
    skill_name = f"integration-skill-{uuid.uuid4().hex[:8]}"
    zip_bytes = _build_zip_with_skill(
        "integration-skill",
        name=skill_name,
        description="integration test",
        content="print('integration')",
    )

    preview = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["total_found"] == 1
    assert preview_payload["total_conflicts"] == 0

    confirm = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": preview_payload["items"][0]["virtual_id"],
                    "name": skill_name,
                    "description": "integration test",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert confirm.status_code == 200
    assert confirm.json() == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 0,
    }

    store = _get_skill_store()
    try:
        assert any(record.name == skill_name for record in store.get_active_skills())
    finally:
        reset_evolution_skill_store()


def test_batch_import_confirm_invalid_virtual_id_returns_structured_detail() -> None:
    client = _make_client()
    zip_bytes = _build_zip_with_skill(
        "integration-skill",
        name=f"virtual-id-{uuid.uuid4().hex[:8]}",
        description="integration test",
        content="print('integration')",
    )
    preview = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", zip_bytes, "application/zip")},
    )
    preview_payload = preview.json()

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": "bad_virtual_id",
                    "name": "invalid-virtual-id",
                    "description": "integration test",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "message": "非法的 virtual_id",
        "error_code": "",
    }


def test_batch_import_conflict_rename_cow_creates_copy_skill() -> None:
    client = _make_client()
    skill_name = f"rename-cow-{uuid.uuid4().hex[:8]}"

    first_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "skill-initial",
            name=skill_name,
            description="v1",
            content="print('v1')",
        ),
    )
    first_item = first_preview["items"][0]
    first_confirm = _confirm_batch_import(
        client,
        first_preview["session_id"],
        [
            {
                "virtual_id": first_item["virtual_id"],
                "name": skill_name,
                "description": "v1",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert first_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 0,
    }

    conflict_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "skill-conflict",
            name=skill_name,
            description="v2",
            content="print('v2')",
        ),
    )
    assert conflict_preview["total_conflicts"] == 1
    conflict_item = conflict_preview["items"][0]
    assert conflict_item["conflict_type"] == "conflict"
    assert conflict_item["existing_skill_id"]

    conflict_confirm = _confirm_batch_import(
        client,
        conflict_preview["session_id"],
        [
            {
                "virtual_id": conflict_item["virtual_id"],
                "name": skill_name,
                "description": "v2",
                "resolution": "rename_cow",
                "existing_skill_id": conflict_item["existing_skill_id"],
            }
        ],
    )
    assert conflict_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 0,
    }

    store = _get_skill_store()
    try:
        names = {record.name for record in store.get_active_skills()}
        assert skill_name in names
        assert f"{skill_name}_copy" in names
    finally:
        reset_evolution_skill_store()


def test_batch_import_conflict_replace_updates_existing_record() -> None:
    client = _make_client()
    skill_name = f"replace-{uuid.uuid4().hex[:8]}"

    first_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "skill-initial",
            name=skill_name,
            description="original",
            content="print('original')",
        ),
    )
    first_item = first_preview["items"][0]
    _confirm_batch_import(
        client,
        first_preview["session_id"],
        [
            {
                "virtual_id": first_item["virtual_id"],
                "name": skill_name,
                "description": "original",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )

    conflict_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "skill-replace",
            name=skill_name,
            description="updated",
            content="print('updated')",
        ),
    )
    assert conflict_preview["total_conflicts"] == 1
    conflict_item = conflict_preview["items"][0]
    existing_skill_id = conflict_item["existing_skill_id"]
    assert isinstance(existing_skill_id, str) and existing_skill_id

    replace_result = _confirm_batch_import(
        client,
        conflict_preview["session_id"],
        [
            {
                "virtual_id": conflict_item["virtual_id"],
                "name": skill_name,
                "description": "updated",
                "resolution": "replace",
                "existing_skill_id": existing_skill_id,
            }
        ],
    )
    assert replace_result == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 0,
    }

    store = _get_skill_store()
    try:
        replaced = store.get_skill(existing_skill_id)
        assert replaced is not None
        assert replaced.name == skill_name
        assert replaced.content == "print('updated')"
        assert not any(
            record.name == f"{skill_name}_copy" for record in store.get_active_skills()
        )
    finally:
        reset_evolution_skill_store()


def test_batch_import_replace_preserves_existing_eval_cases_when_package_has_none() -> (
    None
):
    """replace 覆盖场景：新包不含 evals.json 时，必须保留 DB 中已有回归门禁快照。

    语义：与单包导入 force 覆盖一致——包内无回归门禁时继承 DB 快照，
    不被 INSERT OR REPLACE 整行覆盖清空。
    """
    client = _make_client()
    skill_name = f"preserve-{uuid.uuid4().hex[:8]}"

    # Step 1: 首次导入带 evals.json 的技能，落盘 1 条回归门禁
    first_preview = _preview_batch_import(
        client,
        _build_zip_with_evals(
            "preserve-skill",
            name=skill_name,
            description="v1 with evals",
            content="print('v1')",
        ),
    )
    first_confirm = _confirm_batch_import(
        client,
        first_preview["session_id"],
        [
            {
                "virtual_id": first_preview["items"][0]["virtual_id"],
                "name": skill_name,
                "description": "v1 with evals",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert first_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 1,
    }

    store = _get_skill_store()
    try:
        original = store.get_skill_by_name_version(skill_name)
        assert original is not None
        existing_skill_id = original.skill_id
        assert len(original.eval_cases) == 1
    finally:
        reset_evolution_skill_store()

    # Step 2: replace 覆盖，但新包不含 evals.json
    replace_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "preserve-skill-v2",
            name=skill_name,
            description="v2 no evals",
            content="print('v2')",
        ),
    )
    assert replace_preview["total_conflicts"] == 1
    replace_item = replace_preview["items"][0]
    replace_confirm = _confirm_batch_import(
        client,
        replace_preview["session_id"],
        [
            {
                "virtual_id": replace_item["virtual_id"],
                "name": skill_name,
                "description": "v2 no evals",
                "resolution": "replace",
                "existing_skill_id": existing_skill_id,
            }
        ],
    )
    assert replace_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 1,
    }

    # Step 3: 原 eval_cases 必须保留，不能被清空
    store = _get_skill_store()
    try:
        replaced = store.get_skill(existing_skill_id)
        assert replaced is not None
        assert replaced.content == "print('v2')"
        assert len(replaced.eval_cases) == 1
        assert replaced.eval_cases[0]["message"] == "sum 1 and 2"
    finally:
        reset_evolution_skill_store()


def test_batch_import_replace_preserves_evolution_metadata() -> None:
    """replace 覆盖场景：必须继承原技能的演化元数据。

    语义：与单包导入 force 覆盖一致——replace 仅更新内容/描述/回归门禁，
    版本号、禁用/锁定状态、演化统计、陷阱与验证步骤均保留，不被整行覆盖重置。
    """
    client = _make_client()
    skill_name = f"preserve-meta-{uuid.uuid4().hex[:8]}"

    # Step 1: 首次导入带 evals.json 的技能，落盘回归门禁
    first_preview = _preview_batch_import(
        client,
        _build_zip_with_evals(
            "preserve-meta-skill",
            name=skill_name,
            description="v1 with evals",
            content="print('v1')",
        ),
    )
    first_confirm = _confirm_batch_import(
        client,
        first_preview["session_id"],
        [
            {
                "virtual_id": first_preview["items"][0]["virtual_id"],
                "name": skill_name,
                "description": "v1 with evals",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert first_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 1,
    }

    # Step 2: 模拟技能在演化系统中已积累元数据（v3、锁定、统计、陷阱）
    # 注意：此处保持 is_active=True，禁用状态在 preview 通过后再设置（见 Step 3），
    # 因为批量导入冲突检测基于 get_active_skills（[batch_import.py:106]），
    # 禁用技能不会产生冲突，无法走 replace 路径。
    store = _get_skill_store()
    try:
        original = store.get_skill_by_name_version(skill_name)
        assert original is not None
        existing_skill_id = original.skill_id
        original.lineage.version = 3
        original.evolution_locked = True
        original.metrics.record_applied(success=True)
        original.traps.append({"description": "past failure", "occurrence_count": 1})
        original.verification_steps.append({"step": "run", "expected": "ok"})
        store._save_skill_sync(original)  # noqa: SLF001 - harness 同步落盘入口，避免引入 event loop
    finally:
        reset_evolution_skill_store()

    # Step 3: replace 覆盖，新包不含 evals.json
    replace_preview = _preview_batch_import(
        client,
        _build_zip_with_skill(
            "preserve-meta-v2",
            name=skill_name,
            description="v2 no evals",
            content="print('v2')",
        ),
    )
    assert replace_preview["total_conflicts"] == 1
    replace_item = replace_preview["items"][0]

    # Step 4: preview 与 confirm 之间技能被禁用（防御性场景：replace 不得解除禁用状态）
    store = _get_skill_store()
    try:
        pending = store.get_skill(existing_skill_id)
        assert pending is not None
        pending.is_active = False
        store._save_skill_sync(pending)  # noqa: SLF001
    finally:
        reset_evolution_skill_store()

    replace_confirm = _confirm_batch_import(
        client,
        replace_preview["session_id"],
        [
            {
                "virtual_id": replace_item["virtual_id"],
                "name": skill_name,
                "description": "v2 no evals",
                "resolution": "replace",
                "existing_skill_id": existing_skill_id,
            }
        ],
    )
    assert replace_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 1,
    }

    # Step 5: 演化元数据必须全部保留，内容与回归门禁正确
    store = _get_skill_store()
    try:
        replaced = store.get_skill(existing_skill_id)
        assert replaced is not None
        assert replaced.content == "print('v2')"
        assert replaced.lineage.version == 3
        assert replaced.is_active is False
        assert replaced.evolution_locked is True
        assert replaced.metrics.applied_count == 1
        assert replaced.metrics.success_count == 1
        assert replaced.traps == [{"description": "past failure", "occurrence_count": 1}]
        assert replaced.verification_steps == [{"step": "run", "expected": "ok"}]
        assert len(replaced.eval_cases) == 1
        assert replaced.eval_cases[0]["message"] == "sum 1 and 2"
    finally:
        reset_evolution_skill_store()


def test_batch_import_restores_evals_json_and_excludes_from_disk() -> None:
    client = _make_client()
    skill_name = f"evals-import-{uuid.uuid4().hex[:8]}"

    preview = _preview_batch_import(
        client,
        _build_zip_with_evals(
            "evals-skill",
            name=skill_name,
            description="with evals",
            content="print('with evals')",
        ),
    )
    assert preview["total_found"] == 1

    confirm = _confirm_batch_import(
        client,
        preview["session_id"],
        [
            {
                "virtual_id": preview["items"][0]["virtual_id"],
                "name": skill_name,
                "description": "with evals",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 1,
    }

    store = _get_skill_store()
    try:
        record = next(r for r in store.get_active_skills() if r.name == skill_name)
        assert record.eval_cases == [
            {
                "message": "sum 1 and 2",
                "expected_tools": ["code_interpreter"],
                "require_all": True,
            }
        ]
        # evals.json 不应作为普通文件写入技能目录
        import os

        skill_dir = os.path.dirname(record.path)
        assert not os.path.exists(os.path.join(skill_dir, "evals.json"))
    finally:
        reset_evolution_skill_store()


def test_batch_import_ignores_invalid_evals_json() -> None:
    client = _make_client()
    skill_name = f"bad-evals-{uuid.uuid4().hex[:8]}"

    buffer = io.BytesIO()
    skill_md = f"---\nname: {skill_name}\ndescription: bad evals\n---\nprint('bad')\n"
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bad-evals-skill/SKILL.md", skill_md)
        archive.writestr("bad-evals-skill/evals.json", "{invalid json")

    preview = _preview_batch_import(client, buffer.getvalue())
    assert preview["total_found"] == 1

    confirm = _confirm_batch_import(
        client,
        preview["session_id"],
        [
            {
                "virtual_id": preview["items"][0]["virtual_id"],
                "name": skill_name,
                "description": "bad evals",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 0,
    }

    store = _get_skill_store()
    try:
        record = next(r for r in store.get_active_skills() if r.name == skill_name)
        assert record.eval_cases == []
    finally:
        reset_evolution_skill_store()


def test_batch_import_replace_prefers_package_evals_over_inherited() -> None:
    """replace 覆盖且新包自带 evals.json 时，包内门禁优先于 DB 继承。

    语义：包内 evals 是用户显式提供的新门禁（与单包导入 force 覆盖一致），
    restored_eval_cases 只计包内条数，不叠加继承；演化元数据仍继承。
    """
    client = _make_client()
    skill_name = f"prefer-package-{uuid.uuid4().hex[:8]}"

    # Step 1: 首次导入带 1 条 evals 的技能，DB 落 1 条门禁
    first_preview = _preview_batch_import(
        client,
        _build_zip_with_evals(
            "prefer-package-skill",
            name=skill_name,
            description="v1 with evals",
            content="print('v1')",
        ),
    )
    first_confirm = _confirm_batch_import(
        client,
        first_preview["session_id"],
        [
            {
                "virtual_id": first_preview["items"][0]["virtual_id"],
                "name": skill_name,
                "description": "v1 with evals",
                "resolution": "new",
                "existing_skill_id": None,
            }
        ],
    )
    assert first_confirm["restored_eval_cases"] == 1

    store = _get_skill_store()
    try:
        original = store.get_skill_by_name_version(skill_name)
        assert original is not None
        existing_skill_id = original.skill_id
        assert len(original.eval_cases) == 1
    finally:
        reset_evolution_skill_store()

    # Step 2: replace 覆盖，新包自带 2 条 evals（优先于继承的 1 条）
    package_cases = [
        {"message": "v2 case one", "expected_tools": ["code_interpreter"]},
        {"message": "v2 case two", "expected_tools": ["code_interpreter"]},
    ]
    buffer = io.BytesIO()
    skill_md = (
        f"---\nname: {skill_name}\ndescription: v2 with evals\n---\nprint('v2')\n"
    )
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("prefer-package-v2/SKILL.md", skill_md)
        archive.writestr(
            "prefer-package-v2/evals.json",
            serialize_eval_cases(skill_name, package_cases),
        )

    replace_preview = _preview_batch_import(client, buffer.getvalue())
    assert replace_preview["total_conflicts"] == 1
    replace_item = replace_preview["items"][0]
    replace_confirm = _confirm_batch_import(
        client,
        replace_preview["session_id"],
        [
            {
                "virtual_id": replace_item["virtual_id"],
                "name": skill_name,
                "description": "v2 with evals",
                "resolution": "replace",
                "existing_skill_id": existing_skill_id,
            }
        ],
    )
    assert replace_confirm == {
        "imported_count": 1,
        "skipped_count": 0,
        "restored_eval_cases": 2,
    }

    # Step 3: 门禁取包内 2 条（不叠加继承），演化元数据仍继承
    store = _get_skill_store()
    try:
        replaced = store.get_skill(existing_skill_id)
        assert replaced is not None
        assert replaced.content == "print('v2')"
        assert replaced.lineage.version == 1
        assert replaced.eval_cases == [
            {"message": "v2 case one", "expected_tools": ["code_interpreter"]},
            {"message": "v2 case two", "expected_tools": ["code_interpreter"]},
        ]
        import os

        skill_dir = os.path.dirname(replaced.path)
        assert not os.path.exists(os.path.join(skill_dir, "evals.json"))
    finally:
        reset_evolution_skill_store()
