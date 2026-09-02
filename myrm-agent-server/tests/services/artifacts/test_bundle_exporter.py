"""Unit tests for BundleExporter in Server."""

from __future__ import annotations

import io
import zipfile

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.core.artifacts.manifest import (
    DeliverableCategory,
    DeliverableItem,
    DeliverableManifest,
)

from app.services.artifacts.bundle_exporter import BundleExporter, generate_bundle_readme


def test_bundle_exporter_stream_zip(tmp_path):
    vault = ArtifactVault(str(tmp_path))

    # 存入两个模拟工件
    uri1 = vault.put("文章内容：新品发布核心亮点", filename="wechat.md")
    uri2 = vault.put("排期表数据,2026-09-01,上线", filename="schedule.csv")

    item1 = DeliverableItem(
        id="item-1",
        filename="wechat.md",
        relative_path="02_copywriting_and_content/wechat.md",
        title="微信公众号发布长文",
        category=DeliverableCategory.COPYWRITING,
        vault_uri=uri1,
        size_bytes=len("文章内容：新品发布核心亮点".encode("utf-8")),
    )
    item2 = DeliverableItem(
        id="item-2",
        filename="schedule.csv",
        relative_path="06_schedule_and_plans/schedule.csv",
        title="排期表",
        category=DeliverableCategory.SCHEDULE,
        vault_uri=uri2,
        size_bytes=len("排期表数据,2026-09-01,上线".encode("utf-8")),
    )

    manifest = DeliverableManifest(
        bundle_id="test-bundle-001",
        session_id="test-session-001",
        title="自动化测试交付包",
        items=[item1, item2],
    )

    exporter = BundleExporter(vault)
    chunks = list(exporter.stream_zip(manifest))
    assert len(chunks) > 0

    # 校验生成的完整 ZIP 结构
    zip_bytes = b"".join(chunks)
    zip_file = zipfile.ZipFile(io.BytesIO(zip_bytes))
    namelist = zip_file.namelist()

    assert "manifest.json" in namelist
    assert "README.md" in namelist
    assert "02_copywriting_and_content/wechat.md" in namelist
    assert "06_schedule_and_plans/schedule.csv" in namelist

    readme_text = zip_file.read("README.md").decode("utf-8")
    assert "# 自动化测试交付包" in readme_text
    assert "02_copywriting_and_content/" in readme_text


def test_generate_bundle_readme():
    item = DeliverableItem(
        id="item-test",
        filename="strategy.md",
        title="策略规划总案",
        category=DeliverableCategory.STRATEGY,
        description="战略落地实施路径",
    )
    manifest = DeliverableManifest(
        bundle_id="b-999",
        title="Q4 战略全案",
        items=[item],
    )
    readme = generate_bundle_readme(manifest)
    assert "# Q4 战略全案" in readme
    assert "01_strategy_and_overview/" in readme
    assert "战略落地实施路径" in readme
