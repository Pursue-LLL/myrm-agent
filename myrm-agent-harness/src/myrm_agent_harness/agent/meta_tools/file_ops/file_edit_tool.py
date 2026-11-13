"""文件编辑工具

1. 本文件的 INPUT/OUTPUT/POS 注释

[INPUT]
- core::FileOperationService, OperationContext, OperationType (POS: 文件操作服务和上下文)
- agent.meta_tools._context_recovery::ensure_executor (POS: Executor ContextVar recovery)
- langchain.tools::tool (POS: LangChain 工具装饰器)
- pydantic::BaseModel, Field (POS: 参数验证)

[OUTPUT]
- StrReplaceEditInput, FileEditInput: 文件编辑输入参数模型
- create_file_edit_tool: 创建 file_edit_tool 工厂函数

[POS]
File edit tool. Batch atomic search-and-replace via edits[] with File ID resolution, whitespace-tolerant matching, integrity gates, and verify rollback.

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, model_validator

from myrm_agent_harness.agent.meta_tools._context_recovery import ensure_executor
from myrm_agent_harness.utils.errors import ToolError
from myrm_agent_harness.utils.locale import is_chinese

from .constants import REASON_FIELD_DESCRIPTION
from .core import FileOperationService, OperationContext, OperationType, StrReplaceEdit
from .core.file_edit_normalizer import normalize_edits_payload

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)


class StrReplaceEditInput(BaseModel):
    # One exact-text replacement. A comment, not a docstring: pydantic copies a class docstring into the wire schema
    # as the description of every edit item, and the two fields below already say what it is.

    old_str: str = Field(
        description=(
            "Exact text to replace; must occur exactly once in the file. "
            "Include indentation and enough context to be unique."
        )
    )
    new_str: str = Field(default="", description="Replacement text; empty string deletes.")


class FileEditInput(BaseModel):
    """文件编辑工具输入参数"""

    # The parameter descriptions are the English schema every locale sends; only the tool description is localized.
    path: str = Field(description="File path or @file_id.")
    edits: list[StrReplaceEditInput] = Field(
        description="Ordered replacements applied atomically (max 20, must not overlap)."
    )
    verify_command: str | None = Field(
        default=None,
        description=(
            "Strongly recommended for code files: a check run after editing, e.g. 'python -m py_compile f.py' "
            "or 'node --check f.js'. If it fails all edits are rolled back."
        ),
    )
    reason: str | None = Field(default=None, description=REASON_FIELD_DESCRIPTION)

    @model_validator(mode="before")
    @classmethod
    def normalize_llm_payload(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if payload.get("edits") is not None or "old_str" in payload or "old_string" in payload:
            payload["edits"] = normalize_edits_payload(payload)
        return payload


_FILE_EDIT_TOOL_DESCRIPTION_ZH = (
    "用精确文本替换编辑文件。请始终使用本工具，而不是 bash sed/awk/perl。"
    "编辑已有文件前，先用 file_read_tool 读取一次（普通读取：不带行号范围、不用 preview/stream，这两类读取不算）。"
    "本会话中自己创建或编辑过的文件无需重新读取。"
)

_FILE_EDIT_TOOL_DESCRIPTION_EN = (
    "Edit a file with exact-text replacements. Always use this instead of bash sed/awk/perl. "
    "Before editing an existing file, read it once with file_read_tool (plain read: no line range, not preview/stream; "
    "those do not count). A file you created or edited earlier in this session needs no re-read."
)


def resolve_file_edit_tool_description(locale: str | None = None) -> str:
    """Resolve LLM-facing file_edit_tool description."""
    if is_chinese(locale):
        return _FILE_EDIT_TOOL_DESCRIPTION_ZH
    return _FILE_EDIT_TOOL_DESCRIPTION_EN


def create_file_edit_tool(
    skills: list[SkillMetadata] | None = None,
    *,
    locale: str | None = None,
) -> BaseTool:
    """创建文件编辑工具

    内部使用 FileOperationService，自动处理：
    - File ID 解析（@file_001 → 实际路径）
    - Artifact 自动更新
    - ArtifactTracker 记录
    - 多重匹配检测（防止误替换）
    - 路径安全验证
    - 策略自动选择（StorageBackendStrategy）

    Args:
        skills: MCP 技能列表（保留仅供工具创建时使用）
        locale: 提示词语言

    Returns:
        file_edit_tool 工具函数

    Note:
        StorageProvider 通过 context 注入，不再通过参数传递
    """

    @tool(
        "file_edit_tool",
        description=resolve_file_edit_tool_description(locale),
        args_schema=FileEditInput,
    )
    async def file_edit_func(
        path: str,
        edits: list[StrReplaceEditInput],
        verify_command: str | None = None,
        reason: str | None = None,
        *,  # 强制后续参数为关键字参数
        config: RunnableConfig,  # LangChain 注入的配置
    ) -> str:
        """精确编辑文件（批量原子替换）"""
        try:
            executor = ensure_executor(config)

            edit_tuple = tuple(StrReplaceEdit(old_str=item.old_str, new_str=item.new_str) for item in edits)

            context = OperationContext(
                operation=OperationType.STR_REPLACE,
                executor=executor,
                skills=skills or [],
                path=path,
                edits=edit_tuple,
                verify_command=verify_command,
                reason=reason,
            )

            service = FileOperationService(context)
            result = await service.execute()
            return result

        except ToolError:
            raise
        except FileNotFoundError as e:
            raise ToolError(
                message=str(e),
                user_hint="The file does not exist. Use file_write_tool to create it first.",
            ) from e
        except PermissionError as e:
            raise ToolError(
                message=str(e),
                user_hint="Permission denied. You cannot edit this file.",
            ) from e
        except ValueError as e:
            error_str = str(e).lower()
            if "not found" in error_str:
                hint = (
                    "An old_str was not found. Check exact text (whitespace/indentation) or combine overlapping edits."
                )
            elif "appears" in error_str and "times" in error_str:
                hint = "An old_str matches multiple times. Add surrounding context to make it unique."
            elif "overlap" in error_str:
                hint = "Edits overlap in the file. Merge into one edit or reorder so regions are disjoint."
            elif "syntax" in error_str:
                hint = f"Syntax validation failed. Please fix the syntax error in your edit: {e}"
            else:
                hint = "Invalid edit parameters. Check path and edits array."

            raise ToolError(message=str(e), user_hint=hint) from e
        except Exception as e:
            logger.exception(f"Unexpected error in file_edit_tool: {e}")
            raise ToolError(
                message=f"Unexpected error during file edit: {e}",
                user_hint="An unexpected error occurred. Please check the file path and parameters.",
            ) from e

    return file_edit_func
