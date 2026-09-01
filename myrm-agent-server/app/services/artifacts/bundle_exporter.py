"""Deliverable Bundle Streaming Exporter.

[INPUT]
- myrm_agent_harness.core.artifacts.manifest::DeliverableManifest, DeliverableItem
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault, VAULT_PREFIX
- myrm_agent_harness.agent.security.path_security::safe_join_path

[OUTPUT]
- BundleExporter: class — 恒定 <1MB 内存占用分块流式 ZIP 归档生成器
- stream_bundle_zip: generator — 逐块产出 ZIP 字节流并支持异常断开安全回收

[POS]
Server Business Layer — 将 DeliverableManifest 描述的成套 Vault 对象以流式无缓冲模式打包为 ZIP。
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from collections.abc import Generator

from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from myrm_agent_harness.core.artifacts.manifest import DeliverableManifest

logger = logging.getLogger(__name__)

# 64 KB 分块大小，保持低内存消耗
STREAM_CHUNK_SIZE = 64 * 1024


class ZipStreamBuffer(io.RawIOBase):
    """内存流桥接缓冲区：捕获 zipfile 写入的压缩分块，并通过生成器 yield 出来."""

    def __init__(self) -> None:
        super().__init__()
        self._buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, b: bytes) -> int:  # type: ignore[override]
        self._buffer.extend(b)
        return len(b)

    def read_and_clear(self) -> bytes:
        chunk = bytes(self._buffer)
        self._buffer.clear()
        return chunk


class BundleExporter:
    """生产级成套交付物流式打包导出器"""

    def __init__(self, vault: ArtifactVault) -> None:
        self.vault = vault

    def stream_zip(self, manifest: DeliverableManifest) -> Generator[bytes, None, None]:
        """流式生成 ZIP 压缩包字节流，内存占用恒定在 <1MB.

        包含：
        1. manifest.json 根描述文件
        2. 各个工件按 DeliverableItem.relative_path 组织逻辑子目录
        """
        stream_buf = ZipStreamBuffer()
        zip_file = zipfile.ZipFile(stream_buf, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)

        try:
            # 1. 写入 manifest.json 根描述
            manifest_json = manifest.model_dump_json(indent=2)
            zip_file.writestr("manifest.json", manifest_json.encode("utf-8"))
            chunk = stream_buf.read_and_clear()
            if chunk:
                yield chunk

            # 2. 逐项流式写入各个 DeliverableItem
            for item in manifest.items:
                vault_uri = item.vault_uri
                if not vault_uri or not vault_uri.startswith(VAULT_PREFIX):
                    logger.warning("跳过非法 Vault 指针工件: %s (%s)", item.title, vault_uri)
                    continue

                obj_id = vault_uri[len(VAULT_PREFIX) :]
                obj_path = self.vault.get_object_path(obj_id)
                if not obj_path.exists() or not obj_path.is_file():
                    logger.warning("Vault 物理文件不存在: %s (%s)", item.title, obj_path)
                    continue

                # 规范化相对路径，防路径穿越
                clean_rel_path = self._sanitize_relative_path(item.relative_path or item.title)

                # 写入 ZipEntry 并流式读取源文件写入
                zinfo = zipfile.ZipInfo(clean_rel_path, date_time=time.localtime()[:6])
                zinfo.compress_type = zipfile.ZIP_DEFLATED

                with obj_path.open("rb") as src_f, zip_file.open(zinfo, "w") as dst_z:
                    for file_chunk in iter(lambda: src_f.read(STREAM_CHUNK_SIZE), b""):
                        dst_z.write(file_chunk)
                        chunk = stream_buf.read_and_clear()
                        if chunk:
                            yield chunk

            # 3. 关闭 ZIP 并刷出尾部数据
            zip_file.close()
            chunk = stream_buf.read_and_clear()
            if chunk:
                yield chunk

        except GeneratorExit:
            logger.info("客户端提前中止了交付包流式下载: %s", manifest.bundle_id)
            try:
                zip_file.close()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error("交付包流式打包异常: %s, error=%s", manifest.bundle_id, e, exc_info=True)
            try:
                zip_file.close()
            except Exception:
                pass
            raise

    @staticmethod
    def _sanitize_relative_path(path_str: str) -> str:
        """清洗相对路径，去除前导斜杠和目录穿越"""
        clean = path_str.replace("\\", "/").strip().lstrip("/")
        parts = [p for p in clean.split("/") if p and p not in (".", "..")]
        return "/".join(parts) if parts else "unnamed_artifact"
