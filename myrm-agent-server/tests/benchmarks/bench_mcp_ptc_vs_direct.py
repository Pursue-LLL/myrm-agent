"""Myrm (真实 server) vs Hermes (真实 CLI) 公平基准测试

运行方式:
    cd myrm-agent-server
    uv run python tests/benchmarks/bench_mcp_ptc_vs_direct.py

前置条件:
    - Myrm server 已启动 (./myrm start 或 ./myrm dev)
    - .env.test 配置 BASIC_*
    - Node ``12306-mcp`` 可用（npm install -g 12306-mcp）
    - Hermes CLI 可用（external_reference_project/claw/hermes-agent/）

公平设计:
    - 两者用同一 LLM 模型: MiniMax-M3.1-Flash-Preview
    - 两者用同一 API 协议: OpenAI Chat Completions
    - 两者用同一 MCP 服务: 12306-mcp (stdio)
    - 计时: wall-clock 端到端（从发出请求到收到完整回答）
    - Myrm: 真实 server 的 /api/v1/agents/agent-stream SSE 端点
    - Hermes: 真实 CLI --oneshot
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVER_ROOT))

QUERY = "查询明天从北京到上海的高铁车票"
RUNS_PER_MODE = 3

# ── Credentials ───────────────────────────────────────────────────────────
from tests.support.test_secrets import load_test_secrets

_secrets = load_test_secrets()
API_KEY = _secrets.basic_api_key
BASE_URL = _secrets.basic_base_url
RAW_MODEL = _secrets.basic_model
MODEL = RAW_MODEL.split("/", 1)[1] if "/" in RAW_MODEL else RAW_MODEL

MYRM_SERVER = "http://localhost:8080"


# ── Helpers ───────────────────────────────────────────────────────────────

def _infer_provider_id(raw_model: str) -> str:
    if "/" in raw_model:
        return raw_model.split("/", 1)[0]
    return raw_model


def _resolve_12306_mcp_cfg() -> dict[str, object]:
    """Build 12306 MCP config for Myrm server request."""
    global_bin = shutil.which("12306-mcp")
    if global_bin:
        return {"name": "12306", "type": "stdio", "command": global_bin, "args": [],
                "connect_timeout": 30,
                "description": "12306火车票查询服务，提供实时余票查询、车站信息、经停站、中转换乘等功能"}
    node = shutil.which("node")
    if node:
        candidate = Path(node).resolve().parent.parent / "lib/node_modules/12306-mcp/build/index.js"
        if candidate.is_file():
            return {"name": "12306", "type": "stdio", "command": node, "args": [str(candidate)],
                    "connect_timeout": 30,
                    "description": "12306火车票查询服务"}
    raise RuntimeError("12306-mcp not found. Install: npm install -g 12306-mcp")


# ── Benchmark: Myrm (real server) ────────────────────────────────────────

def _stream_sse(body: dict[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    """Send one SSE request and collect all events. Returns (events, answer_parts)."""
    events: list[dict[str, object]] = []
    answer_parts: list[str] = []
    with httpx.stream(
        "POST",
        f"{MYRM_SERVER}/api/v1/agents/agent-stream",
        json=body,
        timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
    ) as response:
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            events.append(event)
            etype = event.get("type", "")
            if etype == "message":
                content = event.get("data", "")
                if content:
                    answer_parts.append(str(content))
            elif etype == "error":
                err_msg = event.get("error", "") or event.get("data", "")
                print(f"    [Myrm] SSE error: {str(err_msg)[:120]}")
    return events, answer_parts


def bench_myrm_server() -> dict[str, object]:
    """Run benchmark against real Myrm server via SSE stream with auto-approval."""
    try:
        health = httpx.get(f"{MYRM_SERVER}/api/v1/health", timeout=5).json()
        if health.get("status") != "healthy":
            return {"mode": "Myrm Server", "error": f"Server not healthy: {health}"}
    except Exception as e:
        return {"mode": "Myrm Server", "error": f"Server unreachable: {e}"}

    provider_id = _infer_provider_id(RAW_MODEL)
    mcp_cfg = _resolve_12306_mcp_cfg()
    chat_id = f"bench-12306-{uuid.uuid4().hex[:8]}"

    request_body: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": QUERY,
        "action_mode": "agent",
        "modelSelection": {
            "providerId": provider_id,
            "model": MODEL,
            "baseUrl": BASE_URL,
        },
        "enable_memory_auto_extraction": False,
        "enableMemory": False,
        "mcp_cfg": [mcp_cfg],
    }

    t_start = time.monotonic()
    tool_calls_total = 0
    final_answer = ""
    max_rounds = 8

    try:
        for _round_idx in range(max_rounds):
            events, answer_parts = _stream_sse(request_body)

            for ev in events:
                if ev.get("type") == "tasks_steps":
                    tool_calls_total += 1
            if answer_parts:
                final_answer += "".join(answer_parts)

            needs_approval = any(
                ev.get("type") in ("approval_required", "tool_approval_request")
                for ev in events
            )
            hit_iteration_limit = any(
                ev.get("type") == "iteration_limit_reached"
                for ev in events
            )

            if not needs_approval and not hit_iteration_limit:
                break

            request_body = {
                "messageId": str(uuid.uuid4()),
                "chatId": chat_id,
                "query": QUERY,
                "action_mode": "agent",
                "modelSelection": {
                    "providerId": provider_id,
                    "model": MODEL,
                    "baseUrl": BASE_URL,
                },
                "enable_memory_auto_extraction": False,
                "enableMemory": False,
                "mcp_cfg": [mcp_cfg],
            }
            if needs_approval:
                request_body["resumeValue"] = {
                    "decisions": [{"type": "approve", "extensions": {"allowAlways": True}}],
                }
            else:
                request_body["resumeValue"] = {"resume": True}

    except Exception as e:
        return {"mode": "Myrm Server", "error": str(e)}

    total_time = time.monotonic() - t_start

    return {
        "mode": "Myrm Server",
        "rounds": 0,
        "tool_calls": tool_calls_total,
        "total_time": total_time,
        "llm_time": 0.0,
        "mcp_time": 0.0,
        "total_input": 0,
        "total_output": 0,
        "cached": 0,
        "answer_preview": final_answer[:200],
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

    tool_calls_total = 0
    duration_reported = 0.0
    final_answer = ""
    in_response = False
    response_lines: list[str] = []

    for line in proc.stdout.splitlines():
        dur_match = re.search(r"Duration:\s+(\d+)s", line)
        if dur_match:
            duration_reported = float(dur_match.group(1))

        msg_match = re.search(r"(\d+)\s+tool\s+calls?\b", line)
        if msg_match:
            tool_calls_total = int(msg_match.group(1))

        if "\u2624 Hermes" in line:
            in_response = True
            continue
        if in_response and line.startswith("\u2570"):
            in_response = False
            continue
        if in_response:
            clean = line.strip("\u2502").strip()
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
        f"| {r['tool_calls']}次工具调用"
    )
    if r.get("answer_preview"):
        preview = str(r["answer_preview"])[:80].replace("\n", " ")
        print(f"         答案: {preview}...")


def print_summary(label: str, runs: list[dict[str, object]]) -> None:
    valid = [r for r in runs if not r.get("error")]
    if not valid:
        print(f"\n  [{label}] 全部失败")
        for r in runs:
            if r.get("error"):
                print(f"    错误: {r['error']}")
        return

    n = len(valid)
    avg = lambda key: sum(r[key] for r in valid) / n  # noqa: E731

    print(f"\n  [{label}] {n} 次有效 (共 {len(runs)} 次)")
    print(f"    端到端耗时: avg={avg('total_time'):.1f}s | min={min(r['total_time'] for r in valid):.1f}s | max={max(r['total_time'] for r in valid):.1f}s")
    print(f"    工具调用数:  avg={avg('tool_calls'):.1f}")


def main() -> None:
    print("=" * 80)
    print("  Myrm Server (真实) vs Hermes CLI (真实) — 公平基准测试")
    print(f"  模型: {MODEL}")
    print(f"  API: {BASE_URL}")
    print(f"  Myrm: {MYRM_SERVER}")
    print(f"  查询: {QUERY}")
    print(f"  每模式运行: {RUNS_PER_MODE} 次")
    print("=" * 80)

    myrm_results: list[dict[str, object]] = []
    hermes_results: list[dict[str, object]] = []

    for i in range(1, RUNS_PER_MODE + 1):
        print(f"\n── Run {i}/{RUNS_PER_MODE} ──────────────────────────────────")

        # Myrm Server
        print("  [Myrm Server] 执行中...")
        r = bench_myrm_server()
        myrm_results.append(r)
        print_run_result(r, i)

        # Hermes CLI
        print("  [Hermes CLI] 执行中...")
        r = bench_hermes()
        hermes_results.append(r)
        print_run_result(r, i)

    # ── Summary ──
    print("\n" + "=" * 80)
    print("  汇总报告")
    print("=" * 80)
    print_summary("Myrm Server", myrm_results)
    print_summary("Hermes CLI", hermes_results)

    # ── Comparison ──
    print("\n" + "=" * 80)
    print("  对比")
    print("=" * 80)

    for label, results in [("Myrm Server", myrm_results), ("Hermes CLI", hermes_results)]:
        valid = [r for r in results if not r.get("error")]
        if valid:
            avg_time = sum(r["total_time"] for r in valid) / len(valid)
            avg_tools = sum(r["tool_calls"] for r in valid) / len(valid)
            print(f"  {label:<16} avg={avg_time:.1f}s | tools={avg_tools:.1f}")
        else:
            print(f"  {label:<16} FAILED")

    print("\n  注: 两者均使用真实框架、同一模型、同一MCP、同一查询")
    print("  注: Myrm 通过 SSE 端点调用真实 server (含 PTC/middleware/security)")
    print("  注: Hermes 通过 CLI --oneshot 调用真实框架")


if __name__ == "__main__":
    main()
