"""Myrm PTC vs Hermes 公平基准测试

运行方式:
    cd myrm-agent-server
    uv run python tests/benchmarks/bench_mcp_ptc_vs_direct.py

前置条件:
    - .env.test 配置 BASIC_*；禁止在仓库内硬编码 API Key
    - Node ``12306-mcp`` 可用（推荐 ``npm install -g 12306-mcp``）
    - 网络可达 LLM API
    - Hermes CLI 可用（external_reference_project/claw/hermes-agent/）

公平设计:
    - 两者用同一 LLM 模型: MiniMax-M3.1-Flash-Preview
    - 两者用同一 API 协议: OpenAI Chat Completions
    - 两者用同一 MCP 服务: 12306-mcp (stdio)
    - 两者用同一 API Key / Base URL
    - 计时: wall-clock 端到端（含 MCP 启动/框架开销）
    - Myrm: 真实 PTC 流程 + 真实 MCP 执行
    - Hermes: 真实 CLI --oneshot
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVER_ROOT))

QUERY = "查询明天从北京到上海的高铁车票"
RUNS_PER_MODE = 3
MAX_ROUNDS = 10

# ── Credentials ───────────────────────────────────────────────────────────
from tests.support.test_secrets import load_test_secrets

_secrets = load_test_secrets()
API_KEY = _secrets.basic_api_key
BASE_URL = _secrets.basic_base_url
RAW_MODEL = _secrets.basic_model
MODEL = RAW_MODEL.split("/", 1)[1] if "/" in RAW_MODEL else RAW_MODEL


# ── MCP Connection ────────────────────────────────────────────────────────

def _resolve_12306_cmd() -> tuple[str, list[str]]:
    global_bin = shutil.which("12306-mcp")
    if global_bin:
        return global_bin, []
    node = shutil.which("node")
    if node:
        candidate = Path(node).resolve().parent.parent / "lib/node_modules/12306-mcp/build/index.js"
        if candidate.is_file():
            return node, [str(candidate)]
    return "npx", ["-y", "12306-mcp"]


@asynccontextmanager
async def mcp_session_ctx() -> AsyncIterator[ClientSession]:
    """Context manager that yields a live MCP session connected to 12306-mcp."""
    cmd, args = _resolve_12306_cmd()
    params = StdioServerParameters(command=cmd, args=args)
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


# ── LLM Call ──────────────────────────────────────────────────────────────

def llm_call(
    messages: list[dict[str, object]],
    tools: list[dict[str, object]] | None = None,
    *,
    max_retries: int = 3,
) -> dict[str, object]:
    payload: dict[str, object] = {"model": MODEL, "messages": messages, "max_tokens": 4096}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    for attempt in range(max_retries):
        resp = httpx.post(
            f"{BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=120,
        )
        data = resp.json()
        if "error" not in data or "overloaded" not in str(data.get("error", "")):
            return data
        # Retry on overloaded with backoff
        wait = 5 * (attempt + 1)
        print(f"    [API overloaded, retry in {wait}s...]")
        import time as _time
        _time.sleep(wait)
    return data


# ── MCP Tool Schema ──────────────────────────────────────────────────────

async def get_mcp_tool_info(session: ClientSession) -> list[dict[str, object]]:
    """Get MCP tools and build OpenAI-format tool definitions."""
    result = await session.list_tools()
    tool_defs: list[dict[str, object]] = []
    for t in result.tools:
        schema: dict[str, object] = {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema if isinstance(t.input_schema, dict) else {},
            },
        }
        tool_defs.append(schema)
    return tool_defs


# ── PTC Skill Doc Generation (mirrors MCPSkillGenerator) ─────────────────

def build_ptc_skill_doc(tool_defs: list[dict[str, object]]) -> tuple[str, dict[str, str]]:
    """Build SKILL.md (L2) and per-tool docs (L3) from MCP tool schemas.

    Returns (skill_md, tool_docs_map) matching Myrm's MCPSkillGenerator output.
    """
    skill_name = "mcp_12306_skill"
    tool_summaries: list[str] = []
    tool_docs: dict[str, str] = {}

    for tdef in tool_defs:
        func = tdef["function"]
        raw_name = func["name"]
        short_name = raw_name.replace("-", "_")
        desc = func.get("description", "")
        params = func.get("parameters", {})

        # L2: tool summary
        tool_summaries.append(f"- **{short_name}**: {desc[:150]}")

        # L3: detailed doc
        props = params.get("properties", {}) if isinstance(params, dict) else {}
        required = params.get("required", []) if isinstance(params, dict) else []
        param_lines: list[str] = []
        example_parts: list[str] = []
        for pname, pinfo in props.items():
            if not isinstance(pinfo, dict):
                continue
            ptype = pinfo.get("type", "any")
            pdesc = pinfo.get("description", "")
            req_tag = " **(required)**" if pname in required else " (optional)"
            param_lines.append(f"### {pname}{req_tag}\n- **Type**: `{ptype}`\n- **Description**: {pdesc}")
            if pname in required:
                example_parts.append(f'{pname}="..."' if ptype == "string" else f"{pname}=...")

        params_section = "## Parameters\n\n" + "\n\n".join(param_lines) if param_lines else "## Parameters\n\nNone."
        call_example = ", ".join(example_parts)
        tool_docs[short_name] = f"""# {short_name}

## Description

{desc}

{params_section}

## Returns

Returns a **parsed Python object**. Do NOT call `json.loads()` on the result.

## Import & Call Example

```python
from skills.{skill_name} import {short_name}

result = await {short_name}({call_example})
print(result)
```
"""

    # L2: SKILL.md
    skill_md = f"""# 12306 Train Ticket Query Skill

**Skill Name**: `{skill_name}` (use this exact name in import paths and doc paths)

## Available Functions Overview

{chr(10).join(tool_summaries)}

## Usage Guide (Must Follow)

### Step 1: Read function docs via file_read_tool

Path: `/mcp/{skill_name}/<function_name>.md`

### Step 2: ONE bash via bash_code_execute_tool

Import: `from skills.{skill_name} import <func_name>`

Returns are **parsed Python objects** — do NOT `json.loads()`.
"""
    return skill_md, tool_docs


def build_ptc_tools(skill_md_preview: str) -> list[dict[str, object]]:
    """Build the 3 PTC meta-tools (matching real Myrm agent)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "skill_select_tool",
                "description": (
                    "Select and activate bound skills. "
                    "MANDATORY: If the user request relates to any specialized domain in <bound_skills>, "
                    "you MUST select the corresponding skill on turn 1."
                ),
                "parameters": {
                    "type": "object",
                    "required": ["skill_names", "reason"],
                    "properties": {
                        "skill_names": {"type": "array", "items": {"type": "string"},
                                        "description": "Skill names from <bound_skills> catalog"},
                        "reason": {"type": "string", "description": "Brief reason for selecting"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "file_read_tool",
                "description": "Read file. Path: /mcp/{skill_name}/{function_name}.md for MCP skill docs.",
                "parameters": {
                    "type": "object",
                    "required": ["file_path"],
                    "properties": {
                        "file_path": {"type": "string", "description": "File path to read"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bash_code_execute_tool",
                "description": (
                    "Execute Python code. Use 'from skills.xxx import func' for MCP skills. "
                    "End with [RESULT] for final data or [OBSERVATION] to inspect return structure."
                ),
                "parameters": {
                    "type": "object",
                    "required": ["code"],
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                    },
                },
            },
        },
    ]


def build_ptc_system_prompt() -> str:
    """Build system prompt with <bound_skills> catalog (matching real Myrm agent)."""
    return (
        "You are a helpful AI assistant with access to specialized skills.\n\n"
        "<bound_skills>\n"
        "- mcp_12306_skill: 12306 火车票查询服务，支持车票查询、站点查询、中转方案等。"
        "当任务涉及火车票/高铁票/列车查询时，必须首先选择本技能。(mcp)\n"
        "</bound_skills>\n\n"
        "Rules:\n"
        "1. MANDATORY: Select the corresponding skill FIRST before attempting any task.\n"
        "2. After selecting skill, read tool docs via file_read_tool.\n"
        "3. Then execute via bash_code_execute_tool.\n"
        "4. Do NOT guess or hallucinate data."
    )


# ── PTC Bash Executor (parses LLM code → calls MCP) ─────────────────────

def _extract_mcp_calls(code: str, available_tools: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    """Extract MCP function calls from LLM-generated Python code.

    Returns list of (mcp_tool_name, {param: value}).
    """
    calls: list[tuple[str, dict[str, str]]] = []
    # Match patterns like: func_name(param="val", param2="val2")
    # or: await func_name(param="val")
    pattern = re.compile(r"(?:await\s+)?(\w+)\s*\(([^)]*)\)")
    for match in pattern.finditer(code):
        func_name = match.group(1)
        args_str = match.group(2)
        if func_name not in available_tools:
            continue
        # Parse keyword arguments
        kwargs: dict[str, str] = {}
        for kv_match in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))', args_str):
            key = kv_match.group(1)
            val = kv_match.group(2) or kv_match.group(3) or kv_match.group(4)
            kwargs[key] = val
        calls.append((available_tools[func_name], kwargs))
    return calls


async def execute_ptc_bash(
    code: str,
    session: ClientSession,
    available_tools: dict[str, str],
) -> str:
    """Execute PTC bash code by extracting MCP calls and running them."""
    calls = _extract_mcp_calls(code, available_tools)
    if not calls:
        return "[执行完成] 未检测到 MCP 工具调用。如需调用 MCP 工具，请使用 from skills.xxx import func 的方式。"

    results: list[str] = []
    for mcp_name, kwargs in calls:
        try:
            result = await session.call_tool(mcp_name, kwargs)
            content_parts = []
            for c in result.content:
                if hasattr(c, "text"):
                    content_parts.append(c.text)
            results.append(f"[{mcp_name}] {' '.join(content_parts)[:2000]}")
        except Exception as e:
            results.append(f"[{mcp_name}] Error: {e}")

    return "\n".join(results)


# ── Benchmark: Myrm PTC Mode ─────────────────────────────────────────────

async def bench_myrm_ptc() -> dict[str, object]:
    """Run Myrm PTC benchmark with real MCP execution."""
    t_start = time.monotonic()

    async with mcp_session_ctx() as session:
        # Build tool info
        tool_defs = await get_mcp_tool_info(session)
        skill_md, tool_docs = build_ptc_skill_doc(tool_defs)

        # Map short_name → mcp_tool_name for bash execution
        available_tools: dict[str, str] = {}
        for tdef in tool_defs:
            raw_name = tdef["function"]["name"]
            short_name = raw_name.replace("-", "_")
            available_tools[short_name] = raw_name

        ptc_tools = build_ptc_tools(skill_md)
        system_prompt = build_ptc_system_prompt()

        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": QUERY},
        ]
        all_usages: list[dict[str, object]] = []
        all_llm_times: list[float] = []
        mcp_exec_time = 0.0
        tool_calls_total = 0
        rnd = 0

        while rnd < MAX_ROUNDS:
            rnd += 1
            t0 = time.monotonic()
            data = llm_call(messages, ptc_tools)
            llm_elapsed = time.monotonic() - t0
            all_llm_times.append(llm_elapsed)

            if "error" in data:
                print(f"    [PTC] API error: {data['error']}")
                break

            usage = data.get("usage", {})
            all_usages.append(usage)

            choice = data["choices"][0]
            msg = choice["message"]
            tcs = msg.get("tool_calls") or []
            fin = choice.get("finish_reason", "")

            if not tcs or fin == "stop":
                break

            messages.append(msg)
            tool_calls_total += len(tcs)

            for tc in tcs:
                fn = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])

                if fn == "skill_select_tool":
                    content = f"<skills_sop>\n<skill_entry name=\"mcp_12306_skill\" status=\"ready\">\n{skill_md}\n</skill_entry>\n</skills_sop>"
                elif fn == "file_read_tool":
                    file_path = args.get("file_path", "")
                    # Extract tool name from path: /mcp/mcp_12306_skill/{tool_name}.md
                    parts = file_path.strip("/").split("/")
                    tool_name = parts[-1].replace(".md", "") if parts else ""
                    if tool_name in tool_docs:
                        content = tool_docs[tool_name]
                    else:
                        # Try matching with hyphen→underscore normalization
                        normalized = tool_name.replace("-", "_")
                        content = tool_docs.get(normalized, f"Error: file '{file_path}' not found")
                elif fn == "bash_code_execute_tool":
                    code = args.get("code", "")
                    t_mcp = time.monotonic()
                    content = await execute_ptc_bash(code, session, available_tools)
                    mcp_exec_time += time.monotonic() - t_mcp
                else:
                    content = f"Unknown tool: {fn}"

                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content})

    total_time = time.monotonic() - t_start
    final_answer = ""
    for m in reversed(messages):
        if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"]:
            final_answer = m["content"][:200]
            break

    return {
        "mode": "Myrm PTC",
        "rounds": rnd,
        "tool_calls": tool_calls_total,
        "total_time": total_time,
        "llm_time": sum(all_llm_times),
        "mcp_time": mcp_exec_time,
        "total_input": sum(u.get("prompt_tokens", 0) for u in all_usages),
        "total_output": sum(u.get("completion_tokens", 0) for u in all_usages),
        "cached": sum(u.get("prompt_tokens_details", {}).get("cached_tokens", 0) for u in all_usages),
        "answer_preview": final_answer,
    }


# ── Benchmark: Myrm Direct Mode (baseline) ───────────────────────────────

async def bench_myrm_direct() -> dict[str, object]:
    """Run Myrm Direct mode benchmark (inject all MCP schemas)."""
    t_start = time.monotonic()

    async with mcp_session_ctx() as session:
        tool_defs = await get_mcp_tool_info(session)
        messages: list[dict[str, object]] = [{"role": "user", "content": QUERY}]
        all_usages: list[dict[str, object]] = []
        all_llm_times: list[float] = []
        mcp_exec_time = 0.0
        tool_calls_total = 0
        rnd = 0

        while rnd < MAX_ROUNDS:
            rnd += 1
            t0 = time.monotonic()
            data = llm_call(messages, tool_defs)
            llm_elapsed = time.monotonic() - t0
            all_llm_times.append(llm_elapsed)

            if "error" in data:
                print(f"    [Direct] API error: {data['error']}")
                break

            usage = data.get("usage", {})
            all_usages.append(usage)

            choice = data["choices"][0]
            msg = choice["message"]
            tcs = msg.get("tool_calls") or []
            fin = choice.get("finish_reason", "")

            if not tcs or fin == "stop":
                break

            messages.append(msg)
            tool_calls_total += len(tcs)

            for tc in tcs:
                fn = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                t_mcp = time.monotonic()
                try:
                    result = await session.call_tool(fn, args)
                    content_parts = [c.text for c in result.content if hasattr(c, "text")]
                    content = " ".join(content_parts)[:2000]
                except Exception as e:
                    content = f"Error: {e}"
                mcp_exec_time += time.monotonic() - t_mcp
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": content})

    total_time = time.monotonic() - t_start
    final_answer = ""
    for m in reversed(messages):
        if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"]:
            final_answer = m["content"][:200]
            break

    return {
        "mode": "Myrm Direct",
        "rounds": rnd,
        "tool_calls": tool_calls_total,
        "total_time": total_time,
        "llm_time": sum(all_llm_times),
        "mcp_time": mcp_exec_time,
        "total_input": sum(u.get("prompt_tokens", 0) for u in all_usages),
        "total_output": sum(u.get("completion_tokens", 0) for u in all_usages),
        "cached": sum(u.get("prompt_tokens_details", {}).get("cached_tokens", 0) for u in all_usages),
        "answer_preview": final_answer,
    }


# ── Benchmark: Hermes CLI ────────────────────────────────────────────────

def bench_hermes() -> dict[str, object]:
    """Run Hermes CLI benchmark."""
    hermes_root = Path(__file__).resolve().parent.parent.parent.parent.parent / "external_reference_project/claw/hermes-agent"
    hermes_venv = hermes_root / ".venv-test"
    python_bin = hermes_venv / "bin" / "python"
    cli_py = hermes_root / "cli.py"

    if not python_bin.exists() or not cli_py.exists():
        return {"mode": "Hermes", "error": f"Hermes not found: python={python_bin.exists()}, cli={cli_py.exists()}"}

    env = os.environ.copy()
    env["HERMES_HOME"] = "/tmp/hermes_bench_test"
    env["MINIMAX_API_KEY"] = API_KEY

    cmd = [
        str(python_bin), str(cli_py),
        "--model", "MiniMax-M3.1-Flash-Preview",
        "--provider", "custom-minimax",
        "-q", QUERY,
        "--oneshot",
        "-t", "12306",
    ]

    t_start = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env, cwd=str(hermes_root))
    total_time = time.monotonic() - t_start

    # Parse rich-text CLI output for summary line
    tool_calls_total = 0
    duration_reported = 0.0
    final_answer = ""
    in_response = False
    response_lines: list[str] = []

    for line in proc.stdout.splitlines():
        # Parse "Duration:       38s"
        dur_match = re.search(r"Duration:\s+(\d+)s", line)
        if dur_match:
            duration_reported = float(dur_match.group(1))

        # Parse "Messages:       16 (1 user, 14 tool calls)"
        msg_match = re.search(r"(\d+)\s+tool\s+calls?\b", line)
        if msg_match:
            tool_calls_total = int(msg_match.group(1))

        # Capture response content between ╭─ and ╰──
        if "☤ Hermes" in line:
            in_response = True
            continue
        if in_response and line.startswith("╰"):
            in_response = False
            continue
        if in_response:
            # Strip box drawing characters
            clean = line.strip("│").strip()
            if clean:
                response_lines.append(clean)

    if response_lines:
        final_answer = " ".join(response_lines)[:200]

    return {
        "mode": "Hermes",
        "rounds": 0,
        "tool_calls": tool_calls_total,
        "total_time": total_time,
        "llm_time": duration_reported,
        "mcp_time": 0,
        "total_input": 0,
        "total_output": 0,
        "cached": 0,
        "answer_preview": final_answer,
    }


# ── Report ────────────────────────────────────────────────────────────────

def print_run_result(r: dict[str, object], idx: int) -> None:
    mode = r["mode"]
    if r.get("error"):
        print(f"  Run {idx}: [{mode}] ERROR: {r['error']}")
        return
    print(
        f"  Run {idx}: [{mode}] {r['total_time']:.1f}s total "
        f"| LLM {r['llm_time']:.1f}s | MCP {r['mcp_time']:.1f}s "
        f"| {r['rounds']}轮 | {r['tool_calls']}次调用 "
        f"| in={r['total_input']} out={r['total_output']}"
    )
    if r.get("answer_preview"):
        preview = r["answer_preview"][:80].replace("\n", " ")
        print(f"         答案: {preview}...")


def print_summary(label: str, runs: list[dict[str, object]]) -> None:
    valid = [r for r in runs if not r.get("error")]
    if not valid:
        print(f"\n  [{label}] 全部失败")
        return

    n = len(valid)
    avg = lambda key: sum(r[key] for r in valid) / n  # noqa: E731

    print(f"\n  [{label}] {n} 次有效 (共 {len(runs)} 次)")
    print(f"    端到端耗时: avg={avg('total_time'):.1f}s | min={min(r['total_time'] for r in valid):.1f}s | max={max(r['total_time'] for r in valid):.1f}s")
    print(f"    LLM 耗时:   avg={avg('llm_time'):.1f}s")
    print(f"    工具调用数:  avg={avg('tool_calls'):.1f}")
    if any(r.get("total_input", 0) for r in valid):
        print(f"    输入 tokens: avg={avg('total_input'):.0f}")
        print(f"    输出 tokens: avg={avg('total_output'):.0f}")


async def main() -> None:
    print("=" * 80)
    print("  Myrm PTC vs Myrm Direct vs Hermes — 公平基准测试")
    print(f"  模型: {MODEL}")
    print(f"  API: {BASE_URL}")
    print(f"  查询: {QUERY}")
    print(f"  每模式运行: {RUNS_PER_MODE} 次")
    print("=" * 80)

    ptc_results: list[dict[str, object]] = []
    direct_results: list[dict[str, object]] = []
    hermes_results: list[dict[str, object]] = []

    for i in range(1, RUNS_PER_MODE + 1):
        print(f"\n── Run {i}/{RUNS_PER_MODE} ──────────────────────────────────")

        # Myrm PTC
        print("  [Myrm PTC] 执行中...")
        try:
            r = await bench_myrm_ptc()
            ptc_results.append(r)
            print_run_result(r, i)
        except Exception as e:
            print(f"  [Myrm PTC] 失败: {e}")
            ptc_results.append({"mode": "Myrm PTC", "error": str(e)})

        # Myrm Direct
        print("  [Myrm Direct] 执行中...")
        try:
            r = await bench_myrm_direct()
            direct_results.append(r)
            print_run_result(r, i)
        except Exception as e:
            print(f"  [Myrm Direct] 失败: {e}")
            direct_results.append({"mode": "Myrm Direct", "error": str(e)})

        # Hermes
        print("  [Hermes] 执行中...")
        try:
            r = bench_hermes()
            hermes_results.append(r)
            print_run_result(r, i)
        except Exception as e:
            print(f"  [Hermes] 失败: {e}")
            hermes_results.append({"mode": "Hermes", "error": str(e)})

    # ── Summary ──
    print("\n" + "=" * 80)
    print("  汇总报告")
    print("=" * 80)
    print_summary("Myrm PTC", ptc_results)
    print_summary("Myrm Direct", direct_results)
    print_summary("Hermes", hermes_results)

    # ── Comparison table ──
    print("\n" + "=" * 80)
    print("  对比矩阵")
    print("=" * 80)
    print(f"\n  {'指标':<20} {'Myrm PTC':<16} {'Myrm Direct':<16} {'Hermes':<16}")
    print(f"  {'─' * 68}")

    for label, key in [
        ("端到端耗时(s)", "total_time"),
        ("LLM 耗时(s)", "llm_time"),
        ("工具调用次数", "tool_calls"),
        ("输入 tokens", "total_input"),
        ("输出 tokens", "total_output"),
    ]:
        vals: list[str] = []
        for results in [ptc_results, direct_results, hermes_results]:
            valid = [r for r in results if not r.get("error")]
            if valid:
                avg_val = sum(r[key] for r in valid) / len(valid)
                vals.append(f"{avg_val:.1f}" if isinstance(avg_val, float) and avg_val != int(avg_val) else f"{avg_val:.0f}")
            else:
                vals.append("N/A")
        print(f"  {label:<20} {vals[0]:<16} {vals[1]:<16} {vals[2]:<16}")

    print("\n  注: Hermes 的 token 数据不可用(CLI 不导出), 仅比较端到端耗时和工具调用数")
    print("  注: Myrm PTC 需要更多轮次(skill_select→file_read→bash)但每轮 context 更小")
    print("  注: 所有模式均使用相同模型、相同API、相同MCP、相同查询")


if __name__ == "__main__":
    asyncio.run(main())
