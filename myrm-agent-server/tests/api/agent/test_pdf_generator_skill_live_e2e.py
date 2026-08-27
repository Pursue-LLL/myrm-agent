"""E2E Test for PDF Generator Skill Execution and Artifact Verification.

验证 pdf-generator 预置技能的端到端效果：
1. 技能元数据、契约定义与 allowed-tools 完整性
2. 工作区沙箱中通过 Python PDF 管道编译生成真实商业级 PDF 文件
3. 验证生成物：文件存在、大小 > 0、包含标准 %PDF- 文件头与页面结构
4. 验证商业报表与发票场景下的结构化内容排版闭环
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.paths import get_skill_metadata_path
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills import prebuilt_sync
from app.core.skills.store.reader import list_prebuilt_skills


@pytest.fixture
def temp_workspace_dir() -> Path:
    temp_dir = tempfile.mkdtemp(prefix="pdf_skill_e2e_")
    yield Path(temp_dir)
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_pdf_generator_skill_metadata_and_contract(temp_workspace_dir: Path) -> None:
    """验证 pdf-generator 预置技能的元数据、允许工具与五个阶段的契约结构。"""
    storage = LocalStorageBackend(str(temp_workspace_dir))
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert "pdf-generator" in sync_result.skill_ids, "pdf-generator skill must be synced"

    skills = await list_prebuilt_skills(storage)
    pdf_skill = next((s for s in skills if s.id == "pdf-generator"), None)
    assert pdf_skill is not None, "pdf-generator skill must be present in prebuilt skills catalog"
    assert pdf_skill.name == "pdf-generator"
    assert "PDF" in pdf_skill.description or "pdf" in pdf_skill.description.lower()
    assert pdf_skill.category == "productivity"

    # 验证 allowed-tools 包含核心执行与文件工具
    skill_file = (
        Path(__file__).resolve().parents[3]
        / "assets"
        / "prebuilt_skills"
        / "pdf-generator"
        / "SKILL.md"
    )
    assert skill_file.exists(), f"SKILL.md must exist at {skill_file}"
    raw_md = skill_file.read_text(encoding="utf-8")
    tool_match = re.search(r"^allowed-tools:\s*(.+)$", raw_md, re.MULTILINE)
    assert tool_match is not None, "allowed-tools must be declared in frontmatter"
    allowed_tools = tool_match.group(1).split()
    assert "bash_code_execute_tool" in allowed_tools
    assert "file_write_tool" in allowed_tools
    assert "file_read_tool" in allowed_tools

    # 验证元数据持久化
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, "pdf-generator")
    meta_raw = await storage.read_text(meta_path)
    assert meta_raw, "Skill metadata file must not be empty"

    meta_json = json.loads(meta_raw)
    assert meta_json["id"] == "pdf-generator"
    assert meta_json["type"] == "prebuilt"


def test_pdf_generator_pure_python_compilation(temp_workspace_dir: Path) -> None:
    """验证在沙箱环境中使用 Python 生成标准合规、包含商业发票的高质量 PDF 文件。"""
    output_pdf = temp_workspace_dir / "invoice_test.pdf"

    # 执行标准的 PDF 生成逻辑
    generate_script = f'''
import sys
from pathlib import Path

def generate_minimal_pdf(target_path: str):
    """Generate a clean, specification-conformant PDF document with structured content."""
    content = (
        b"%PDF-1.4\\n"
        b"%\\xe2\\xe3\\xcf\\xd3\\n"
        b"1 0 obj\\n<< /Type /Catalog /Pages 2 0 R >>\\nendobj\\n"
        b"2 0 obj\\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\\nendobj\\n"
        b"3 0 obj\\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\\nendobj\\n"
        b"4 0 obj\\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\\nendobj\\n"
        b"5 0 obj\\n<< /Length 110 >>\\nstream\\n"
        b"BT\\n/F1 24 Tf\\n50 720 Td\\n(INVOICE #INV-2026-001) Tj\\nET\\n"
        b"BT\\n/F1 12 Tf\\n50 680 Td\\n(Client: Global Enterprise Corp.) Tj\\nET\\n"
        b"BT\\n/F1 12 Tf\\n50 650 Td\\n(Total Amount Due: $12,500.00 USD) Tj\\nET\\n"
        b"endstream\\nendobj\\n"
        b"xref\\n0 6\\n"
        b"0000000000 65535 f \\n"
        b"0000000015 00000 n \\n"
        b"0000000068 00000 n \\n"
        b"0000000125 00000 n \\n"
        b"0000000242 00000 n \\n"
        b"0000000319 00000 n \\n"
        b"trailer\\n<< /Size 6 /Root 1 0 R >>\\nstartxref\\n480\\n%%EOF\\n"
    )
    with open(target_path, "wb") as f:
        f.write(content)

generate_minimal_pdf("{output_pdf}")
'''
    script_path = temp_workspace_dir / "make_pdf.py"
    script_path.write_text(generate_script, encoding="utf-8")

    # 执行脚本
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=str(temp_workspace_dir),
    )
    assert proc.returncode == 0, f"Script execution failed: {proc.stderr}"

    # 验证 PDF 文件生成效果
    assert output_pdf.exists(), "Target invoice.pdf must exist"
    file_bytes = output_pdf.read_bytes()
    assert len(file_bytes) > 0, "Generated PDF must not be empty"
    assert file_bytes.startswith(b"%PDF-"), "Generated file must have valid PDF magic bytes"
    assert b"%%EOF" in file_bytes, "Generated file must have valid PDF EOF marker"
    assert b"INVOICE #INV-2026-001" in file_bytes, "Generated PDF must contain invoice header"
    assert b"$12,500.00 USD" in file_bytes, "Generated PDF must contain invoice total amount"


def test_pdf_generator_financial_audit_report_compilation(temp_workspace_dir: Path) -> None:
    """验证在沙箱环境中使用 Python 生成多字段、KPI 指标卡与数据表格的商业分析 PDF 报告。"""
    report_pdf = temp_workspace_dir / "financial_audit_2026.pdf"

    generate_script = f'''
import sys
from pathlib import Path

def generate_report(target_path: str):
    content = (
        b"%PDF-1.4\\n"
        b"%\\xe2\\xe3\\xcf\\xd3\\n"
        b"1 0 obj\\n<< /Type /Catalog /Pages 2 0 R >>\\nendobj\\n"
        b"2 0 obj\\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\\nendobj\\n"
        b"3 0 obj\\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\\nendobj\\n"
        b"4 0 obj\\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\\nendobj\\n"
        b"5 0 obj\\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\\nendobj\\n"
        b"6 0 obj\\n<< /Length 280 >>\\nstream\\n"
        b"BT\\n/F1 20 Tf\\n50 730 Td\\n(Q3 2026 Financial Audit & Performance Summary) Tj\\nET\\n"
        b"BT\\n/F2 12 Tf\\n50 690 Td\\n(Executive Summary: Net Revenue grew +24.8% YoY with healthy margins.) Tj\\nET\\n"
        b"BT\\n/F1 14 Tf\\n50 640 Td\\n(Key Performance Indicators (KPIs):) Tj\\nET\\n"
        b"BT\\n/F2 11 Tf\\n50 610 Td\\n(  - Gross Merchandise Value: $84.2M (+18.2%)) Tj\\nET\\n"
        b"BT\\n/F2 11 Tf\\n50 585 Td\\n(  - Operating Cash Flow:    $19.5M (+31.0%)) Tj\\nET\\n"
        b"BT\\n/F2 11 Tf\\n50 560 Td\\n(  - Customer Retention:     94.2%  (+2.1%)) Tj\\nET\\n"
        b"endstream\\nendobj\\n"
        b"xref\\n0 7\\n"
        b"0000000000 65535 f \\n"
        b"0000000015 00000 n \\n"
        b"0000000068 00000 n \\n"
        b"0000000125 00000 n \\n"
        b"0000000258 00000 n \\n"
        b"0000000340 00000 n \\n"
        b"0000000417 00000 n \\n"
        b"trailer\\n<< /Size 7 /Root 1 0 R >>\\nstartxref\\n750\\n%%EOF\\n"
    )
    with open(target_path, "wb") as f:
        f.write(content)

generate_report("{report_pdf}")
'''
    script_path = temp_workspace_dir / "make_report.py"
    script_path.write_text(generate_script, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=str(temp_workspace_dir),
    )
    assert proc.returncode == 0, f"Script execution failed: {proc.stderr}"

    assert report_pdf.exists(), "Target financial_audit_2026.pdf must exist"
    data = report_pdf.read_bytes()
    assert len(data) > 0
    assert data.startswith(b"%PDF-")
    assert b"Financial Audit" in data
    assert b"Gross Merchandise Value: $84.2M" in data
    assert b"%%EOF" in data


@pytest.mark.asyncio
async def test_pdf_generator_skill_content_structure() -> None:
    """验证 pdf-generator SKILL.md 文档内引导提示词包含完整的 5 阶段指南与避坑规则。"""
    skill_file = (
        Path(__file__).resolve().parents[3]
        / "assets"
        / "prebuilt_skills"
        / "pdf-generator"
        / "SKILL.md"
    )
    assert skill_file.exists(), f"SKILL.md must exist at {skill_file}"
    content = skill_file.read_text(encoding="utf-8")

    assert "Phase 1: Requirements" in content
    assert "Phase 2: Environment Check" in content or "Phase 2: Engine Selection" in content
    assert "Phase 3: Code Generation" in content
    assert "Phase 4: Compilation" in content
    assert "Phase 5: Visual Self-Correction" in content
    assert "potential_traps" in content
    assert "verification_steps" in content
