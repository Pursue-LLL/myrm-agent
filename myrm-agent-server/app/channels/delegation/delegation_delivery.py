"""Deliverable artifact scanning, oversized auto-fallback, and mobile rich delivery card builder.

Discovers multi-modal deliverables (PPTX, XLSX, PDF, HTML, Diff, Media) generated
within the task sandbox workspace, computes checksums, applies 20MB channel
bandwidth safety caps with deep-link fallback, and formats delivery cards.

[INPUT]
- .delegation_models::DelegationTask, DeliveryArtifact, ApprovalRequest
- Local sandbox workspace path strings.

[OUTPUT]
- scan_workspace_artifacts: Discover deliverables within workspace folder.
- build_delivery_card_content: Render structured completion report for mobile IM.
- build_approval_card_content: Render structured authorization prompt with options.
- format_file_size: Human-readable byte formatting helper.

[POS]
Delivery and presentation layer for app/channels/delegation/.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path

from .delegation_models import ApprovalRequest, DelegationTask, DeliveryArtifact

# Standard channel direct attachment threshold (20MB)
DEFAULT_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

_SUPPORTED_DELIVERABLE_EXTS: frozenset[str] = frozenset(
    {
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".docx",
        ".doc",
        ".pdf",
        ".html",
        ".htm",
        ".zip",
        ".tar.gz",
        ".diff",
        ".patch",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".mp4",
        ".csv",
        ".json",
        ".md",
    }
)


def format_file_size(size_bytes: int) -> str:
    """Format byte integer to readable human string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def compute_file_sha256(file_path: Path, max_bytes_to_read: int = 10 * 1024 * 1024) -> str:
    """Compute SHA256 hex digest for a file."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
                if f.tell() >= max_bytes_to_read:
                    break
        return h.hexdigest()
    except Exception:
        return ""


def scan_workspace_artifacts(
    workspace_dir: str | Path,
    *,
    max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
    server_base_url: str = "",
) -> list[DeliveryArtifact]:
    """Scan sandbox directory for newly created deliverable files.

    Args:
        workspace_dir: Sandbox folder to scan.
        max_attachment_bytes: File size cap for native IM transfer (default: 20MB).
        server_base_url: Optional server URL prefix for direct download links.

    Returns:
        List of DeliveryArtifact metadata objects.
    """
    path = Path(workspace_dir)
    if not path.is_dir():
        return []

    artifacts: list[DeliveryArtifact] = []
    for root, _, files in os.walk(path):
        for f in files:
            # Skip hidden files and temp locks
            if f.startswith((".", "~$", "__")):
                continue

            file_path = Path(root) / f
            ext = file_path.suffix.lower()
            if ext not in _SUPPORTED_DELIVERABLE_EXTS:
                continue

            try:
                stat = file_path.stat()
                size = stat.st_size
                if size == 0:
                    continue

                mime, _ = mimetypes.guess_type(str(file_path))
                mime_type = mime or "application/octet-stream"
                sha = compute_file_sha256(file_path)
                is_oversized = size > max_attachment_bytes

                download_url = ""
                if server_base_url:
                    rel = file_path.relative_to(path)
                    download_url = f"{server_base_url.rstrip('/')}/api/artifacts/download?path={rel}"

                artifacts.append(
                    DeliveryArtifact(
                        file_name=file_path.name,
                        file_path=str(file_path.resolve()),
                        file_size_bytes=size,
                        mime_type=mime_type,
                        sha256_hash=sha,
                        is_oversized=is_oversized,
                        direct_download_url=download_url,
                        created_at=stat.st_mtime,
                    )
                )
            except Exception:
                continue

    # Sort newest first
    artifacts.sort(key=lambda a: a.created_at, reverse=True)
    return artifacts


def build_delivery_card_content(
    task: DelegationTask,
    artifacts: list[DeliveryArtifact] | None = None,
    *,
    tracking_deep_link: str = "",
    server_base_url: str = "",
) -> str:
    """Render structured completion report and artifact delivery card for mobile IM.

    Args:
        task: Completed DelegationTask instance.
        artifacts: List of discovered DeliveryArtifact objects.
        tracking_deep_link: Optional deep-link URL to WebUI/Tauri workspace.
        server_base_url: Optional base URL for direct download URLs.

    Returns:
        Structured Markdown text formatted for mobile display.
    """
    duration_str = ""
    if task.started_at and task.completed_at:
        elapsed = int(task.completed_at - task.started_at)
        mins, secs = divmod(elapsed, 60)
        duration_str = f"{mins}分{secs}秒" if mins else f"{secs}秒"

    status_symbol = "✅" if task.status.value == "completed" else "❌"
    lines = [
        f"{status_symbol} **任务交付通知 (后台委派任务执行完成)**",
        f"• **任务编号**：`{task.task_id}`",
        f"• **任务内容**：{task.raw_prompt[:60]}{'...' if len(task.raw_prompt) > 60 else ''}",
    ]

    if duration_str:
        lines.append(f"• **总共耗时**：{duration_str}")

    if task.result_summary:
        lines.extend(["", "**📊 执行结果摘要：**", task.result_summary])
    elif task.error_message:
        lines.extend(["", "**⚠️ 异常信息：**", f"`{task.error_message}`"])

    # Artifact list
    effective_artifacts = artifacts or task.artifacts
    if effective_artifacts:
        lines.extend(["", "**📦 生成交付物清单：**"])
        for idx, art in enumerate(effective_artifacts, start=1):
            size_fmt = format_file_size(art.file_size_bytes)
            icon = "📊" if art.file_name.endswith((".xlsx", ".csv")) else ("📑" if art.file_name.endswith(".pptx") else "📄")
            if art.is_oversized:
                lines.append(f"{idx}. {icon} **{art.file_name}** `[{size_fmt} · 大文件已生成下载链接]`")
                if art.direct_download_url:
                    lines.append(f"   ↳ [点击极速下载]({art.direct_download_url})")
            else:
                if art.direct_download_url:
                    lines.append(f"{idx}. {icon} **[{art.file_name}]({art.direct_download_url})** `[{size_fmt}]`")
                else:
                    lines.append(f"{idx}. {icon} **{art.file_name}** `[{size_fmt}]`")

    if tracking_deep_link:
        lines.extend(["", f"🔗 [在桌面端/WebUI打开完整工作区]({tracking_deep_link})"])

    return "\n".join(lines)


def build_approval_card_content(req: ApprovalRequest) -> str:
    """Render interactive authorization prompt for high-risk operations.

    Args:
        req: Active ApprovalRequest payload.

    Returns:
        Formatted Markdown card text.
    """
    risk_icons = {
        "low": "🟢 低风险",
        "medium": "🟡 中风险",
        "high": "🟠 高风险",
        "critical": "🔴 极高风险",
    }
    risk_tag = risk_icons.get(req.risk_level.value, "⚠️ 待审批")

    lines = [
        f"🛡️ **后台沙箱请求远程授权审批** `[{risk_tag}]`",
        f"• **任务编号**：`{req.task_id}`",
        f"• **审批单号**：`{req.request_id}`",
        f"• **待执行操作**：`{req.action_name}`",
        f"• **操作详情**：{req.action_summary}",
        "",
        "👉 **请在移动端直接点击按钮或回复编号确认：**",
    ]
    for idx, opt in enumerate(req.options, start=1):
        opt_label = "允许执行" if opt == "approve" else "拒绝并跳过"
        lines.append(f"`[{idx}]` {opt_label}")

    return "\n".join(lines)
