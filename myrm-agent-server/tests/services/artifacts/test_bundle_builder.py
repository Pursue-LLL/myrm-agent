"""Tests for bundle_builder deliverable packaging."""

import io
import json
import zipfile

from myrm_agent_harness.agent.artifacts.bundle_manifest import (
    DeliverableCategory,
    DeliverableItem,
    DeliverableManifest,
)
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.bundle_builder import (
    build_zip_deliverable_bundle,
    generate_bundle_readme,
    sanitize_path_segment,
)


def test_sanitize_path_segment():
    assert sanitize_path_segment("foo/bar\\baz") == "foo_bar_baz"
    assert sanitize_path_segment("../../etc/passwd") == "etc_passwd"
    assert sanitize_path_segment("合法文档.md") == "合法文档.md"


def test_generate_bundle_readme():
    manifest = DeliverableManifest(
        title="测试交付全案",
        description="测试描述说明",
        items=[
            DeliverableItem(
                id="1",
                filename="strategy.md",
                relative_path="01_strategy_and_overview/strategy.md",
                category=DeliverableCategory.STRATEGY,
                description="核心策略文档",
            )
        ],
    )
    readme = generate_bundle_readme(manifest)
    assert "# 测试交付全案" in readme
    assert "核心策略文档" in readme
    assert "01_strategy_and_overview/" in readme


def test_build_zip_deliverable_bundle(tmp_path):
    vault_root = tmp_path / "vault_root"
    vault = ArtifactVault(str(vault_root))

    # Create dummy artifact in vault
    vault_uri = vault.put("hello world strategy", filename="strategy.md")

    version = ArtifactVersion(
        id="v-1",
        artifact_id="art-1",
        vault_uri=vault_uri,
        sha256_hash="dummy-sha",
        creator_id="user-1",
        created_at="2026-09-01T00:00:00",
    )
    artifact = Artifact(
        id="art-1",
        name="strategy.md",
        description="主策略",
        versions=[version],
    )

    buf = build_zip_deliverable_bundle([artifact], vault)
    assert isinstance(buf, io.BytesIO)

    with zipfile.ZipFile(buf, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "README.md" in namelist
        assert any("strategy.md" in name for name in namelist)

        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert len(manifest_data["items"]) == 1


def test_build_zip_deliverable_bundle_dual_source_sandbox_fallback(tmp_path):
    vault_root = tmp_path / "vault_root"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    vault = ArtifactVault(str(vault_root))

    # Artifact without vault object, but physically generated in workspace sandbox
    sandbox_file = workspace_root / "07_code_and_scripts" / "run_script.py"
    sandbox_file.parent.mkdir(parents=True, exist_ok=True)
    sandbox_file.write_text("print('hello sandbox')", encoding="utf-8")

    manifest = DeliverableManifest(
        title="双源容错交付包",
        description="测试沙箱实体回退",
        fact_check_sheet_uri="vault://fcs_12345",
        evidence_sources=["vault://raw_source_1.pdf"],
        items=[
            DeliverableItem(
                id="art-sandbox",
                filename="run_script.py",
                relative_path="07_code_and_scripts/run_script.py",
                category=DeliverableCategory.CODE,
                description="沙箱中执行生成的脚本",
            )
        ],
    )

    buf = build_zip_deliverable_bundle([], vault, manifest=manifest, workspace_root=workspace_root)
    assert isinstance(buf, io.BytesIO)

    with zipfile.ZipFile(buf, "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "README.md" in namelist
        assert "07_code_and_scripts/run_script.py" in namelist
        assert zf.read("07_code_and_scripts/run_script.py").decode("utf-8") == "print('hello sandbox')"

        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_data["fact_check_sheet_uri"] == "vault://fcs_12345"
        assert manifest_data["evidence_sources"] == ["vault://raw_source_1.pdf"]

