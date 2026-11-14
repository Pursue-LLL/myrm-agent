"""文件读取工具

[INPUT]
- langchain.tools::tool (POS: LangChain 工具装饰器)
- core::FileOperationService (POS: 文件操作服务)
- agent.security.redact::redact_sensitive_text, redact_file_text (POS: 工具输出脱敏；逐文件脱敏：源码文件只对含字符串字面量的行做按变量名脱敏)
- backends.skills.types::SkillMetadata (POS: MCP 技能元数据)
- core.file_read::build_multimodal_result, append_media_text_parts, process_text_paths (POS: file_read 执行处理器)
- core.file_read::assert_paths_allowed_for_read, assert_evicted_uploaded_read_scope, partition_urls (POS: 读取范围守卫：disabled skill 拦截与 Fast 轨范围)
- file_search.path_hint::suggest_similar_paths, format_path_not_found_hint, find_existing_unicode_path (POS: 路径不存在提示与 Unicode 探测自愈)
- core.security.path::is_blocked_device_path (POS: Pre-IO 设备路径安全阻断)
- utils.vault_read::is_vault_uri, path_base, read_vault_paths_to_parts (POS: vault:// URI 读取)
- mcp_read_next_step_hint::append_mcp_docs_next_step_hint (POS: MCP 函数文档批量读取后的下一步操作提示)
- utils.*_reader (POS: 多模态与文档读取)
- utils.errors::ToolError (POS: 工具错误类型)

[OUTPUT]
- create_file_read_tool(): 工厂函数，创建 file_read_tool（可选 path_policy=evicted_uploaded）
- file_read_tool: LangChain Tool（本地/MCP/File ID/vault:// 路径、批量读取、行号范围、多模态、Office/Jupyter 解析）

[POS]
File read tool factory and orchestration. Supports full workspace reads or Fast-track
evicted_uploaded scope (UECD spill, spilled long pastes and chat uploads only). Heavy read
logic and the read-scope guards live in core/file_read/.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from langchain.tools import tool
from langchain_core.messages.content import create_text_block
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, field_validator, model_validator

from myrm_agent_harness.agent.context_management.context import (
    extract_context_from_runnable_config,
)
from myrm_agent_harness.agent.meta_tools._context_recovery import ensure_executor
from myrm_agent_harness.agent.meta_tools.file_search.path_hint import (
    find_existing_unicode_path,
    format_path_not_found_hint,
    suggest_similar_paths,
)
from myrm_agent_harness.agent.security.path_security import is_blocked_device_path
from myrm_agent_harness.agent.security.redact import redact_file_text, redact_sensitive_text
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.core.security.tool_registry import PATHS_ALIAS_KEYS, coerce_path_list
from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor, get_executor
from myrm_agent_harness.utils.errors import ToolError
from myrm_agent_harness.utils.locale import is_chinese

from .constants import REASON_FIELD_DESCRIPTION
from .core.file_read import (
    append_media_text_parts,
    assert_evicted_uploaded_read_scope,
    assert_paths_allowed_for_read,
    build_multimodal_result,
    partition_urls,
    process_text_paths,
)
from .core.mcp_read_next_step_hint import append_mcp_docs_next_step_hint
from .utils.document_reader import is_document_path
from .utils.image_reader import is_image_path
from .utils.pdf_reader import is_pdf_path
from .utils.vault_read import is_vault_uri, path_base, read_vault_paths_to_parts
from .utils.video_reader import is_video_path

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)

FileReadPathPolicy = Literal["full", "evicted_uploaded"]


class FileReadInput(BaseModel):
    """文件读取工具输入参数"""

    # The parameter descriptions are the English schema every locale sends; only the tool description is localized.
    paths: list[str] = Field(
        description=(
            "Files or directories. Line range suffix (text/code files only): 'f.py:1-50' or 'f.py:100-' (to the end). "
            "Also accepts @file_id, vault://uuid[:range] and /mcp/... paths."
        )
    )

    mode: str = Field(
        default="all",
        description=(
            "'all' (default); 'preview': first 1000 lines; 'stream': first page of a very large file. "
            "Read further parts with a line range."
        ),
    )

    parse_mode: str | None = Field(
        default=None,
        description=(
            "'structure': outline / table of contents (目录/大纲): headings or symbols with line numbers (Markdown, code), "
            "PDF headings with page numbers, structure metadata (Word, Excel, PPTX); 'content': full text; "
            "'audit': Excel audit JSON. Default: full text (large Excel files default to 'structure')."
        ),
    )

    preserve_in_context: bool = Field(
        default=False,
        description="Keep this content through context compaction. Only for critical specs or skill files.",
    )

    reason: str | None = Field(default=None, description=REASON_FIELD_DESCRIPTION)

    @model_validator(mode="before")
    @classmethod
    def normalize_input_aliases(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("paths") is None:
            for k in PATHS_ALIAS_KEYS:
                if data.get(k) is not None:
                    data["paths"] = data[k]
                    break
        return data

    @field_validator("paths", mode="before")
    @classmethod
    def normalize_paths(cls, v: object) -> list[object] | None:
        return coerce_path_list(v)


_FILE_READ_TOOL_DESCRIPTION_ZH = (
    "读取文件内容（支持批量）或列出目录；也支持图片、视频、PDF、Office 文档（docx/xlsx/pptx）和 ipynb。"
    "仅限本地/沙箱路径，网页请用 web_fetch_tool。"
)

_FILE_READ_TOOL_DESCRIPTION_EN = (
    "Read files (batch) or list a directory. Also reads images, video, PDF, Office documents (docx/xlsx/pptx) and ipynb. "
    "Local/sandbox paths only; use web_fetch_tool for URLs."
)


def resolve_file_read_tool_description(locale: str | None = None) -> str:
    """Resolve LLM-facing file_read_tool description."""
    if is_chinese(locale):
        return _FILE_READ_TOOL_DESCRIPTION_ZH
    return _FILE_READ_TOOL_DESCRIPTION_EN


def create_file_read_tool(
    skills: list[SkillMetadata] | None = None,
    *,
    path_policy: FileReadPathPolicy = "full",
    locale: str | None = None,
) -> BaseTool:
    """创建 file_read_tool（详见 core/file_read 与 FileOperationService）。"""

    @tool(
        "file_read_tool",
        description=resolve_file_read_tool_description(locale),
        args_schema=FileReadInput,
    )
    async def file_read_func(
        paths: list[str],
        mode: str = "all",
        parse_mode: str | None = None,
        reason: str | None = None,
        preserve_in_context: bool = False,
        *,
        config: RunnableConfig,
    ) -> str | Sequence[object]:
        valid_paths: list[str] = []
        try:
            # 1. Pre-IO Device path security intercept
            for raw_p in paths:
                base = path_base(raw_p) if not is_vault_uri(raw_p) else raw_p
                if is_blocked_device_path(raw_p) or is_blocked_device_path(base):
                    raise ToolError(
                        message=f"Access to device path is blocked: {raw_p}",
                        user_hint="Access to device paths and reserved system devices is forbidden.",
                    )

            valid_paths, url_refusal = partition_urls(paths)
            url_errors = [url_refusal] if url_refusal else []

            if not valid_paths:
                if url_refusal:
                    return url_refusal
                raise ValueError("No valid paths provided.")

            # 2. Unicode normalization candidate probing & self-healing
            workspace_root = workspace_root_var.get().strip() or None
            healed_paths: list[str] = []
            for p in valid_paths:
                if is_vault_uri(p) or p.startswith("/mcp/"):
                    healed_paths.append(p)
                    continue
                base = path_base(p)
                range_suffix = p[len(base) :]
                found = find_existing_unicode_path(base, base_dir=workspace_root)
                if found and found != base:
                    healed_paths.append(f"{found}{range_suffix}")
                else:
                    healed_paths.append(p)
            valid_paths = healed_paths

            ctx = extract_context_from_runnable_config(config)
            try:
                executor: CodeExecutor | None = ensure_executor(config)
            except RuntimeError:
                executor = get_executor()
            await assert_paths_allowed_for_read(valid_paths, config, executor)
            if path_policy == "evicted_uploaded":
                chat_id = str(ctx.get("chat_id") or "")
                await assert_evicted_uploaded_read_scope(valid_paths, chat_id=chat_id, executor=executor)
            supports_vision = bool(ctx.get("supports_vision", False))
            supports_video = bool(ctx.get("supports_video", False))
            vision_fallback_model_cfg = ctx.get("vision_fallback_model_cfg")
            vision_fallback_model_cfgs = ctx.get("vision_fallback_model_cfgs")
            video_fallback_model_cfgs = ctx.get("video_fallback_model_cfgs")

            image_paths = [p for p in valid_paths if is_image_path(path_base(p)) and not is_vault_uri(p)]
            pdf_paths = [p for p in valid_paths if is_pdf_path(path_base(p)) and not is_vault_uri(p)]
            document_paths = [p for p in valid_paths if is_document_path(path_base(p)) and not is_vault_uri(p)]
            video_paths = [p for p in valid_paths if is_video_path(path_base(p)) and not is_vault_uri(p)]
            vault_paths = [p for p in valid_paths if is_vault_uri(p)]
            text_paths = [
                p
                for p in valid_paths
                if not is_vault_uri(p)
                and not is_image_path(path_base(p))
                and not is_pdf_path(path_base(p))
                and not is_document_path(path_base(p))
                and not is_video_path(path_base(p))
            ]

            has_multimodal = (image_paths or pdf_paths or video_paths) and executor is not None
            use_multimodal = has_multimodal and (
                supports_vision
                or supports_video
                or vision_fallback_model_cfg is not None
                or vision_fallback_model_cfgs is not None
                or video_fallback_model_cfgs is not None
            )
            has_documents = bool(document_paths) and executor is not None

            if (use_multimodal or has_documents) and executor is not None:
                blocks = await build_multimodal_result(
                    image_paths,
                    pdf_paths,
                    document_paths,
                    text_paths,
                    vault_paths,
                    executor,
                    skills,
                    reason,
                    url_errors,
                    supports_vision=supports_vision,
                    supports_video=supports_video,
                    vision_fallback_model_cfg=vision_fallback_model_cfg,
                    vision_fallback_model_cfgs=vision_fallback_model_cfgs,
                    video_fallback_model_cfgs=video_fallback_model_cfgs,
                    video_paths=video_paths,
                    parse_mode=parse_mode,
                    mode=mode,
                    config=config,
                )
                if preserve_in_context:
                    blocks.insert(0, create_text_block("<preserve_context>\n"))
                    blocks.append(create_text_block("\n</preserve_context>"))
                return blocks

            text_parts: list[str] = list(url_errors)
            await append_media_text_parts(
                text_parts,
                image_paths=image_paths,
                pdf_paths=pdf_paths,
                document_paths=document_paths,
                video_paths=video_paths,
                executor=executor,
                supports_vision=supports_vision,
                supports_video=supports_video,
                vision_fallback_model_cfg=vision_fallback_model_cfg,
                vision_fallback_model_cfgs=vision_fallback_model_cfgs,
                video_fallback_model_cfgs=video_fallback_model_cfgs,
                parse_mode=parse_mode,
            )

            if vault_paths:
                text_parts.extend(await read_vault_paths_to_parts(vault_paths, executor, mode, config=config))

            text_parts = [redact_sensitive_text(part) for part in text_parts]
            if text_paths:
                file_parts = await process_text_paths(
                    text_paths,
                    executor,
                    skills,
                    reason,
                    mode,
                    config=config,
                    parse_mode=parse_mode,
                )
                text_parts.extend(
                    redact_file_text(path_base(path), part) for path, part in zip(text_paths, file_parts, strict=True)
                )

            result = "\n\n".join(text_parts) if text_parts else "No results."
            final_text = append_mcp_docs_next_step_hint(result, text_paths)
            if preserve_in_context:
                final_text = f"<preserve_context>\n{final_text}\n</preserve_context>"
            return final_text

        except ToolError:
            raise
        except FileNotFoundError as e:
            hint_path = path_base(valid_paths[0]) if valid_paths else str(e)
            suggestions = suggest_similar_paths(hint_path)
            raise ToolError(
                message=str(e),
                user_hint=format_path_not_found_hint(hint_path, suggestions),
            ) from e
        except PermissionError as e:
            raise ToolError(
                message=str(e),
                user_hint="Permission denied. You cannot perform this operation on this path.",
            ) from e
        except ValueError as e:
            raise ToolError(
                message=str(e),
                user_hint="Invalid parameter. Please check the file path format and try again.",
            ) from e
        except Exception as e:
            logger.exception("Unexpected error in file_read_tool: %s", e)
            raise ToolError(
                message=f"Unexpected error during file read: {e}",
                user_hint="An unexpected error occurred. Please try again or check the file path.",
            ) from e

    return file_read_func
