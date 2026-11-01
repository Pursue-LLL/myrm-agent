"""MCP Metadata Extractor

负责解析和提取 MCP 调用元数据。
 不再注册引用，只返回结构化元数据。

[INPUT]
- agent.skills.mcp.ipc_proxy::get_mcp_trace_nonce (POS: 标记 nonce 来源)
- toolkits.code_execution.executors.common.mcp_markers (POS: 标记的形状，与输出脱敏器共用)
- toolkits.code_execution.executors.models::scrub_sensitive_info (POS: 对解码出的内容脱敏)

[OUTPUT]
- MCPMetadataExtractor: class — M C P Metadata Extractor

[POS]
MCP Metadata Extractor.

Markers are authenticated by a per-process nonce issued to the child through its
generated client code. Two properties follow, and both matter:

- A tool result cannot forge a citation by embedding the marker delimiters, because it
  cannot guess the nonce.
- A tool result cannot truncate or swallow a genuine marker by containing ``__END__``,
  because the payload is base64 and the delimiter is nonce-bound.

Without a live nonce the extractor trusts nothing: it returns the stdout and no
metadata. Emitting unauthenticated metadata is the failure this guards against.

The output scrubber lets marker-shaped spans through verbatim (it would otherwise
destroy them), so this module scrubs what it takes out of a marker and any marker-shaped
span it does not authenticate. Nothing marker-shaped leaves here unscrubbed.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable

from myrm_agent_harness.toolkits.code_execution.executors.common.mcp_markers import (
    MARKER_PREFIX,
    MARKER_SUFFIX,
    scrub_marker_spans,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import scrub_sensitive_info

logger = logging.getLogger(__name__)

# 类型别名：按技能分组的 MCP 调用数据
# 格式：{skill_name: [{"tool": tool_name, "result": result_data}, ...]}
type SkillCallsDict = dict[str, list[dict[str, str]]]

# 返回当前有效标记 nonce 的回调；无可用 nonce 时返回 None。
type NonceProvider = Callable[[], str | None]

_NOTE_MAX_ENTRIES = 10
_NOTE_NAME_CHARS = 80


class MCPMetadataExtractor:
    """MCP 元数据提取器

     职责：
    - 从执行输出中提取 MCP 调用标记
    - 按技能分组 MCP 调用
    - 返回结构化元数据（供业务层使用）
    - 清理和格式化输出内容
    """

    def __init__(self, nonce_provider: NonceProvider | None = None) -> None:
        """初始化提取器。

        Args:
            nonce_provider: 返回当前有效 nonce 的回调，默认读取运行中的 IPC 服务端。
                延迟解析而非构造时固定，这样服务端重启后不会继续接受旧 nonce。
        """
        self._nonce_provider: NonceProvider = nonce_provider or _live_trace_nonce

    def extract_metadata(self, stdout: str) -> tuple[str, dict[str, object]]:
        """从输出中提取 MCP 调用标记，返回清洁输出和元数据

         处理流程：
        1. 解析所有带合法 nonce 的调用标记
        2. 按 MCP 服务（技能）分组
        3. 返回结构化元数据（供业务层使用）
        4. 移除原始标记，返回清洁输出

        Args:
            stdout: 原始标准输出

        Returns:
            元组：(清洁的输出, MCP 元数据字典)
        """
        remaining, skill_calls = self._split_markers(stdout)
        if not skill_calls:
            return remaining, {}

        # 如果用户没有显式 print 输出，使用 MCP result 数据
        clean_stdout = remaining.strip() or self._extract_mcp_results(skill_calls)
        return clean_stdout, self._build_metadata(skill_calls)

    def extract_completed_calls(self, stdout: str) -> tuple[str, str]:
        """Failure-path counterpart of :meth:`extract_metadata`.

        Returns the stdout without authenticated markers and one line naming the tool
        calls the script completed before it failed ("" when there were none). A failing
        script's output is the model's only record of what already ran; hiding the
        completed calls invites a retry that repeats their effects.
        """
        remaining, skill_calls = self._split_markers(stdout)
        return remaining, self._completed_calls_note(skill_calls)

    def _split_markers(self, stdout: str) -> tuple[str, SkillCallsDict]:
        """Take the authenticated markers out of ``stdout``.

        Returns the remaining text and the calls the markers carried. Marker-shaped
        spans that cannot be authenticated stay visible (so a forged one is seen, not
        promoted to metadata) but are scrubbed, because the output scrubber skipped them.
        """
        if not stdout or MARKER_PREFIX not in stdout:
            return stdout, {}

        nonce = self._nonce_provider()
        if not nonce:
            # No live nonce: nothing in this output can be authenticated.
            logger.warning(" MCP 标记存在但无可用 nonce，跳过提取（不产出不可信元数据）")
            return scrub_marker_spans(stdout, scrub_sensitive_info), {}

        pattern = self._compile_pattern(nonce)
        matches = pattern.findall(stdout)
        if not matches:
            logger.info(" 未找到带合法 nonce 的 MCP 标记，返回原始输出")
            return scrub_marker_spans(stdout, scrub_sensitive_info), {}

        # 全部解析失败时同样只移除已认证的标记，避免污染用户可见输出。
        remaining = scrub_marker_spans(pattern.sub("", stdout), scrub_sensitive_info)
        return remaining, self._group_calls_by_skill(matches)

    @classmethod
    def _compile_pattern(cls, nonce: str) -> re.Pattern[str]:
        """构建 nonce 绑定的标记正则。

        Payload 是 base64，字符集固定为 ``A-Za-z0-9+/=``，因此不需要非贪婪匹配，
        也不存在定界符冲突的可能。
        """
        escaped = re.escape(nonce)
        return re.compile(rf"{MARKER_PREFIX}{escaped}([A-Za-z0-9+/=]*){MARKER_SUFFIX}{escaped}\n?")

    def _group_calls_by_skill(self, matches: list[str]) -> SkillCallsDict:
        """按技能分组 MCP 调用

        Args:
            matches: 正则匹配到的 base64 payload 列表

        Returns:
            按技能名称分组的调用字典
        """
        skill_calls: SkillCallsDict = {}

        for match in matches:
            data = self._decode_payload(match)
            if data is None:
                continue

            skill = data.get("s")
            tool = data.get("t")
            result = data.get("r")
            if not isinstance(skill, str) or not skill:
                continue

            skill_calls.setdefault(skill, []).append(
                {
                    "tool": tool if isinstance(tool, str) else "",
                    "result": scrub_sensitive_info(result) if isinstance(result, str) else "",
                }
            )

        return skill_calls

    @staticmethod
    def _decode_payload(payload: str) -> dict[str, object] | None:
        """Decode one base64 payload into its call record."""
        if not payload:
            return None
        try:
            raw = base64.b64decode(payload, validate=True)
            decoded = json.loads(raw.decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(f" 解析 MCP 数据标记失败: {exc}")
            return None
        if not isinstance(decoded, dict):
            logger.warning(" 解析 MCP 数据标记失败: payload 不是对象")
            return None
        return decoded

    @staticmethod
    def _completed_calls_note(skill_calls: SkillCallsDict) -> str:
        """Name the calls in ``skill_calls`` once each with a count ("" when empty)."""
        counts: dict[str, int] = {}
        for skill_name, calls in skill_calls.items():
            for call in calls:
                # Names come from the MCP server; keep each one a short single token run.
                label = " ".join(f"{skill_name}.{call.get('tool', '')}".split())[:_NOTE_NAME_CHARS]
                counts[label] = counts.get(label, 0) + 1
        if not counts:
            return ""
        shown = [f"{label} x{count}" for label, count in list(counts.items())[:_NOTE_MAX_ENTRIES]]
        hidden = len(counts) - len(shown)
        suffix = f", +{hidden} more" if hidden > 0 else ""
        return (
            "MCP tool calls this script completed before it failed "
            f"(re-running them repeats their effects): {', '.join(shown)}{suffix}"
        )

    def _build_metadata(self, skill_calls: SkillCallsDict) -> dict[str, object]:
        """构建 MCP 元数据（遵循 metadata.sources 标准约定）

        Args:
            skill_calls: 按技能分组的调用字典

        Returns:
            包含 sources 字段的元数据字典，供 SourceTracker 自动处理
        """
        sources: list[dict[str, object]] = []
        total_calls = 0

        for skill_name, calls in skill_calls.items():
            call_records = [{"tool_name": c.get("tool", ""), "result_preview": c.get("result", "")} for c in calls]
            sources.append(
                {
                    "type": "mcp",
                    "skill_name": skill_name,
                    "calls": call_records,
                }
            )
            total_calls += len(calls)
            logger.info(f" 提取 MCP 元数据: {skill_name} ({len(calls)} 次调用)")

        return {
            "sources": sources,
            "total_calls": total_calls,
        }

    def _extract_mcp_results(self, skill_calls: SkillCallsDict) -> str:
        """从 MCP 调用中提取 result 数据

        当用户没有显式 print 输出时，使用 MCP 返回的数据。

        Args:
            skill_calls: 按技能分组的调用字典

        Returns:
            拼接后的 result 内容
        """
        logger.info(" 用户无 print 输出，使用 MCP result 数据")

        mcp_results = []
        for _skill_name, calls in skill_calls.items():
            for call in calls:
                tool = call.get("tool", "unknown")
                result = call.get("result", "")
                if result:
                    mcp_results.append(f"[{tool}] {result}")

        return "\n\n".join(mcp_results) if mcp_results else ""


def _live_trace_nonce() -> str | None:
    """Default nonce source: the running IPC server's marker nonce."""
    from myrm_agent_harness.agent.skills.mcp.ipc_proxy import get_mcp_trace_nonce

    return get_mcp_trace_nonce()


__all__ = ["MCPMetadataExtractor", "NonceProvider"]
