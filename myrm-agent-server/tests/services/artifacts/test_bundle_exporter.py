"""Unit tests for BundleExporter in Server."""

import io
import zipfile

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.core.artifacts.manifest import (
    DeliverableCategory,
    DeliverableItem,
    DeliverableManifest,
)

from app.services.artifacts.bundle_exporter import BundleExporter


def test_bundle_exporter_stream_zip(tmp_path):
    vault = ArtifactVault(str(tmp_path))

    # 存入两个模拟工件
    uri1 = vault.put("文章内容：新品发布核心亮点", filename="wechat.md")
    uri2 = vault.put("排期表数据,2026-09-01,上线", filename="schedule.csv")

    item1 = DeliverableItem(
        id="item-1",
        relative_path="articles/wechat.md",
        title="微信公众号发布长文",
        category=DeliverableCategory.ARTICLE,
        vault_uri=uri1,
        size_bytes=len("文章内容：新品发布核心亮点".encode("utf-8")),
    )
    item2 = DeliverableItem(
        id="item-2",
        relative_path="sheets/schedule.csv",
        title="排期表",
        category=DeliverableCategory.DATA_SHEET,
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
    assert "articles/wechat.md" in namelist
    assert "sheets/schedule.csv" in namelist

    assert zip_file.read("articles/wechat.md").decode("utf-8") == "文章内容：新品发布核心亮点"
