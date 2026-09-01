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
