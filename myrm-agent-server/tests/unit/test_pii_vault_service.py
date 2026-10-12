"""Unit tests for PiiVaultService in server layer.

[POS]
Server unit tests verifying transparent PII pseudonymization, local vault storage,
and reverse reconstruction.
"""

from __future__ import annotations

from app.schemas.pii_vault import (
    DesanitizePiiRequest,
    DetectPiiRequest,
    SanitizePiiRequest,
)
from app.services.security.pii_vault_service import PiiVaultService


def test_pii_vault_service_sanitize_and_desanitize() -> None:
    service = PiiVaultService()
    session_id = "sess_unit_pii"

    # 1. Detect PII probe
    detect_req = DetectPiiRequest(
        text="联系人姓名：赵六，联系电话：13912345678，邮箱：zhaoliu@corp.com"
    )
    detect_res = service.detect_pii(detect_req)
    assert detect_res.count == 3
    types = [m.entity_type for m in detect_res.matches]
    assert "chinese_name" in types
    assert "phone_number" in types
    assert "email" in types

    # 2. Sanitize outbound text
    san_req = SanitizePiiRequest(
        text="联系人姓名：赵六，联系电话：13912345678，邮箱：zhaoliu@corp.com",
        session_id=session_id,
    )
    san_res = service.sanitize_text(san_req)
    assert san_res.placeholders_count == 3
    assert "赵六" not in san_res.sanitized_text
    assert "13912345678" not in san_res.sanitized_text
    assert "zhaoliu@corp.com" not in san_res.sanitized_text

    # Extract name placeholder
    name_match = next(m for m in san_res.entities_detected if m.entity_type == "chinese_name")
    name_placeholder = name_match.placeholder

    # 3. Simulate LLM response referencing placeholder and reverse desanitize
    llm_output = f"已为客户 {name_placeholder} 成功办理业务。"
    desan_req = DesanitizePiiRequest(
        text=llm_output,
        session_id=session_id,
    )
    desan_res = service.desanitize_text(desan_req)
    assert desan_res.restored_count == 1
    assert "赵六" in desan_res.restored_text
    assert name_placeholder not in desan_res.restored_text
    assert desan_res.restored_text == "已为客户 赵六 成功办理业务。"

    # 4. Clear session
    clear_res = service.clear_session(session_id)
    assert clear_res.cleared is True
    assert len(service.vault.list_mappings(session_id)) == 0
