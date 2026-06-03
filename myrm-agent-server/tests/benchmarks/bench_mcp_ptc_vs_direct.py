"""PTC vs 直连模式 token/延迟基准测试

运行方式:
    cd myrm-agent-server
    uv run python tests/benchmarks/bench_mcp_ptc_vs_direct.py

前置条件:
    - .env.test 配置 BASIC_*（可选 LITE_*）；禁止在仓库内硬编码 API Key
    - uvx 可用 (用于 stdio MCP)
    - 网络可达 LLM API
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SERVER_ROOT))


_UVX_PATH = os.environ.get("UVX_PATH") or shutil.which("uvx") or "uvx"
QUERY = "查询明天从北京到上海的高铁车票"


RUNS_PER_MODEL = 3


def _load_model_configs() -> list[dict[str, str]]:
    from tests.support.test_secrets import load_test_secrets

    secrets = load_test_secrets()
    configs: list[dict[str, str]] = []
    if secrets.has_basic_credentials:
        configs.append(
            {
                "label": "basic",
                "api_key": secrets.basic_api_key,
                "base_url": secrets.basic_base_url,
                "model": secrets.basic_model,
            }
        )
    if secrets.has_lite_credentials:
        configs.append(
            {
                "label": "lite",
                "api_key": secrets.lite_api_key,
                "base_url": secrets.lite_base_url,
                "model": secrets.lite_model,
            }
        )
    if not configs:
        raise RuntimeError(
            "No credentials in .env.test. Set BASIC_API_KEY, BASIC_BASE_URL, BASIC_MODEL "
            "(and optionally LITE_*)."
        )
    return configs


def _resolve_uvx() -> str:
    if Path(_UVX_PATH).exists():
        return _UVX_PATH
    found = shutil.which("uvx")
    if found:
        return found
    raise RuntimeError("uvx not found")


async def _get_mcp_tools() -> tuple[list[object], list[dict[str, object]], int]:
    """连接 MCP 获取工具列表, 返回 (tools, tool_defs, schema_tokens)"""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    uvx_cmd = _resolve_uvx()
    client = MultiServerMCPClient(
        {"12306": {"command": uvx_cmd, "args": ["mcp-server-12306"], "transport": "stdio"}}
    )
    tools = await client.get_tools()

    tool_defs = []
    total_chars = 0
    for tool in tools:
        args_schema = tool.args_schema
        if hasattr(args_schema, "model_json_schema"):
            params = args_schema.model_json_schema()
        elif isinstance(args_schema, dict):
            params = args_schema
        else:
            params = {}
        schema = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": params,
            },
        }
        total_chars += len(json.dumps(schema, ensure_ascii=False))
        tool_defs.append(schema)

    return tools, tool_defs, total_chars // 4


def _llm_call(api_key: str, base_url: str, model: str,
              messages: list[dict[str, object]],
              tools: list[dict[str, object]] | None = None) -> dict[str, object]:
    import httpx
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_tokens": 4096,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = httpx.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    return resp.json()


async def bench_direct(api_key: str, base_url: str, model: str,
                       tools: list[object], tool_defs: list[dict[str, object]],
                       schema_tokens: int) -> dict[str, object]:
    """直连模式基准测试"""
    messages: list[dict[str, object]] = [{"role": "user", "content": QUERY}]
    all_usages: list[dict[str, object]] = []
    all_times: list[float] = []
    total_exec = 0.0
    rnd = 0

    while rnd < 10:
        rnd += 1
        t0 = time.monotonic()
        data = _llm_call(api_key, base_url, model, messages, tool_defs)
        elapsed = time.monotonic() - t0
        all_times.append(elapsed)

        usage = data.get("usage", {})
        all_usages.append(usage)

        choice = data["choices"][0]
        tcs = choice["message"].get("tool_calls") or []
        fin = choice.get("finish_reason", "")

        if not tcs or fin == "stop":
            break

        messages.append(choice["message"])
        for tc in tcs:
            fn = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            target = next((t for t in tools if t.name == fn), None)
            if not target:
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": f"Error: {fn} not found"})
                continue
            t1 = time.monotonic()
            result = await target.ainvoke(args)
            total_exec += time.monotonic() - t1
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": str(result)[:1000]})

    return {
        "rounds": rnd,
        "total_time": sum(all_times) + total_exec,
        "llm_time": sum(all_times),
        "mcp_time": total_exec,
        "total_input": sum(u.get("prompt_tokens", 0) for u in all_usages),
        "total_output": sum(u.get("completion_tokens", 0) for u in all_usages),
        "cached": sum(u.get("prompt_tokens_details", {}).get("cached_tokens", 0) for u in all_usages),
        "schema_per_round": schema_tokens,
    }


async def bench_ptc(api_key: str, base_url: str, model: str) -> dict[str, object]:
    """PTC 模式基准测试（模拟 skill_select -> file_read -> bash -> response）"""
    ptc_tools = [
        {"type": "function", "function": {
            "name": "skill_select_tool",
            "description": "Select skills:\n<skills>\n- mcp_12306_skill: 12306火车票查询服务 (mcp)\n</skills>",
            "parameters": {"type": "object", "required": ["skill_names", "reason"],
                           "properties": {"skill_names": {"type": "array", "items": {"type": "string"}},
                                          "reason": {"type": "string"}}},
        }},
        {"type": "function", "function": {
            "name": "file_read_tool",
            "description": "Read file. Path: /mcp/{skill_name}/{function_name}.md",
            "parameters": {"type": "object", "required": ["file_path"],
                           "properties": {"file_path": {"type": "string"}}},
        }},
        {"type": "function", "function": {
            "name": "bash_code_execute_tool",
            "description": "Execute Python code. Use 'from skills.xxx import func' for MCP.",
            "parameters": {"type": "object", "required": ["code"],
                           "properties": {"code": {"type": "string"}}},
        }},
    ]

    schema_tokens = len(json.dumps(ptc_tools, ensure_ascii=False)) // 4

    skill_md = """# 12306 Skill
**Skill Name**: `mcp_12306_skill`
## Available Functions
- **query_left_ticket**: 查询两站之间指定日期的余票信息
- **get_station_name_by_keyword**: 根据关键字搜索车站信息
- **query_ticket_price**: 查询指定车次的票价
- **query_train_station_list**: 查询指定车次的经停站
- **query_transfer_plan**: 查询中转换乘方案
## Usage Guide
### Step 1: Read docs: `/mcp/mcp_12306_skill/{function}.md`
### Step 2: Call via bash: `from skills.mcp_12306_skill import func`
Returns parsed Python objects, do NOT json.loads().
"""

    tool_doc = """# query_left_ticket
## Parameters
### train_date **(required)** - string - 查询日期 YYYY-MM-DD
### from_station **(required)** - string - 出发站名
### to_station **(required)** - string - 到达站名
## Example
```python
from skills.mcp_12306_skill import query_left_ticket
result = query_left_ticket(train_date="2026-06-01", from_station="北京", to_station="上海")
```"""

    bash_result = """[执行成功]
G1 北京南-上海虹桥 06:36-11:12 4h36m 二等座¥553 有票
G3 北京南-上海虹桥 07:00-11:28 4h28m 二等座¥553 有票
G5 北京南-上海虹桥 08:00-12:32 4h32m 二等座¥553 有票
G7 北京南-上海虹桥 09:00-13:28 4h28m 二等座¥553 有票
G9 北京南-上海虹桥 10:00-14:32 4h32m 二等座¥553 有票"""

    mock_responses = {"skill_select_tool": skill_md, "file_read_tool": tool_doc, "bash_code_execute_tool": bash_result}

    messages: list[dict[str, object]] = [{"role": "user", "content": QUERY}]
    all_usages: list[dict[str, object]] = []
    all_times: list[float] = []
    rnd = 0

    while rnd < 8:
        rnd += 1
        t0 = time.monotonic()
        data = _llm_call(api_key, base_url, model, messages, ptc_tools)
        elapsed = time.monotonic() - t0
        all_times.append(elapsed)

        usage = data.get("usage", {})
        all_usages.append(usage)

        choice = data["choices"][0]
        tcs = choice["message"].get("tool_calls") or []
        fin = choice.get("finish_reason", "")

        if not tcs or fin == "stop":
            break

        messages.append(choice["message"])
        for tc in tcs:
            fn = tc["function"]["name"]
            content = mock_responses.get(fn, "[ok]")
            messages.append({"role": "tool", "tool_call_id": tc.get("id", f"tc{rnd}"), "content": content})

    return {
        "rounds": rnd,
        "total_time": sum(all_times),
        "llm_time": sum(all_times),
        "mcp_time": 0,
        "total_input": sum(u.get("prompt_tokens", 0) for u in all_usages),
        "total_output": sum(u.get("completion_tokens", 0) for u in all_usages),
        "cached": sum(u.get("prompt_tokens_details", {}).get("cached_tokens", 0) for u in all_usages),
        "schema_per_round": schema_tokens,
    }


async def main() -> None:
    print("=" * 80)
    print("        PTC vs 直连模式基准测试 - 多模型多轮")
    print(f"        查询: {QUERY}")
    print(f"        每模型运行: {RUNS_PER_MODEL} 次")
    print("=" * 80)

    # 预连接 MCP 获取工具
    print("\n[准备] 连接 MCP 获取工具...")
    tools, tool_defs, schema_tokens = await _get_mcp_tools()
    print(f"[准备] 获取 {len(tools)} 个工具, schema ~{schema_tokens} tokens\n")

    all_results: list[dict[str, object]] = []

    for model_cfg in _load_model_configs():
        label = model_cfg["label"]
        api_key = model_cfg["api_key"]
        base_url = model_cfg["base_url"]
        model = model_cfg["model"]

        print(f"\n{'=' * 80}")
        print(f"  模型: {label} ({model})")
        print(f"{'=' * 80}")

        for run_idx in range(1, RUNS_PER_MODEL + 1):
            print(f"\n--- {label} Run {run_idx}/{RUNS_PER_MODEL} ---")

            # 直连
            print("  [直连] 开始...")
            try:
                # 每次新建 MCP 连接以模拟真实场景
                fresh_tools, fresh_defs, fresh_schema = await _get_mcp_tools()
                d = await bench_direct(api_key, base_url, model, fresh_tools, fresh_defs, fresh_schema)
                print(f"  [直连] {d['rounds']}轮 | {d['total_time']:.1f}s | in={d['total_input']} out={d['total_output']} cached={d['cached']}")
            except Exception as e:
                print(f"  [直连] 失败: {e}")
                d = {"rounds": 0, "total_time": 0, "llm_time": 0, "mcp_time": 0,
                     "total_input": 0, "total_output": 0, "cached": 0, "schema_per_round": schema_tokens, "error": str(e)}

            # PTC
            print("  [PTC]  开始...")
            try:
                p = await bench_ptc(api_key, base_url, model)
                print(f"  [PTC]  {p['rounds']}轮 | {p['total_time']:.1f}s | in={p['total_input']} out={p['total_output']} cached={p['cached']}")
            except Exception as e:
                print(f"  [PTC]  失败: {e}")
                p = {"rounds": 0, "total_time": 0, "llm_time": 0, "mcp_time": 0,
                     "total_input": 0, "total_output": 0, "cached": 0, "schema_per_round": 0, "error": str(e)}

            all_results.append({"model": label, "run": run_idx, "direct": d, "ptc": p})

    # ========== 汇总报告 ==========
    print("\n\n" + "=" * 80)
    print("                         📊 汇总报告")
    print("=" * 80)

    for model_cfg in _load_model_configs():
        label = model_cfg["label"]
        model_runs = [r for r in all_results if r["model"] == label]

        if not model_runs:
            continue

        print(f"\n{'─' * 80}")
        print(f"  {label}")
        print(f"{'─' * 80}")

        d_runs = [r["direct"] for r in model_runs if not r["direct"].get("error")]
        p_runs = [r["ptc"] for r in model_runs if not r["ptc"].get("error")]

        if not d_runs or not p_runs:
            print(f"  ⚠️  部分运行失败, 直连成功={len(d_runs)}, PTC成功={len(p_runs)}")
            continue

        def avg(lst: list[dict[str, object]], key: str) -> float:
            vals = [r[key] for r in lst if isinstance(r.get(key), (int, float))]
            return sum(vals) / len(vals) if vals else 0

        print(f"\n  {'指标':<22} {'直连(avg)':<18} {'PTC(avg)':<18} {'比率'}")
        print(f"  {'-' * 72}")

        metrics = [
            ("推理轮次", "rounds"),
            ("总耗时(s)", "total_time"),
            ("LLM耗时(s)", "llm_time"),
            ("总输入tokens", "total_input"),
            ("总输出tokens", "total_output"),
            ("缓存命中tokens", "cached"),
        ]

        for mlabel, key in metrics:
            d_avg = avg(d_runs, key)
            p_avg = avg(p_runs, key)
            ratio = p_avg / d_avg if d_avg > 0 else 0

            if key in ("total_time", "llm_time"):
                d_str = f"{d_avg:.1f}"
                p_str = f"{p_avg:.1f}"
            else:
                d_str = f"{d_avg:.0f}"
                p_str = f"{p_avg:.0f}"

            winner = "PTC更优" if ratio < 0.95 else ("直连更优" if ratio > 1.05 else "持平")
            print(f"  {mlabel:<22} {d_str:<18} {p_str:<18} {ratio:.2f}x ({winner})")

        # 每轮明细
        print("\n  轮次明细:")
        for r in model_runs:
            ri = r["run"]
            d = r["direct"]
            p = r["ptc"]
            d_err = f" ERR:{d['error'][:30]}" if d.get("error") else ""
            p_err = f" ERR:{p['error'][:30]}" if p.get("error") else ""
            print(f"    Run{ri}: 直连 {d['rounds']}轮 {d['total_time']:.1f}s in={d['total_input']} out={d['total_output']}{d_err}"
                  f" | PTC {p['rounds']}轮 {p['total_time']:.1f}s in={p['total_input']} out={p['total_output']}{p_err}")

    # 总结
    print(f"\n{'=' * 80}")
    print("                         📋 总结论")
    print(f"{'=' * 80}")

    total_d_input = sum(r["direct"]["total_input"] for r in all_results if not r["direct"].get("error"))
    total_p_input = sum(r["ptc"]["total_input"] for r in all_results if not r["ptc"].get("error"))
    total_d_time = sum(r["direct"]["total_time"] for r in all_results if not r["direct"].get("error"))
    total_p_time = sum(r["ptc"]["total_time"] for r in all_results if not r["ptc"].get("error"))
    n_valid = sum(1 for r in all_results if not r["direct"].get("error") and not r["ptc"].get("error"))

    if n_valid > 0:
        print(f"\n  有效测试: {n_valid} 次")
        print(f"  全局输入token: 直连 {total_d_input} vs PTC {total_p_input} (PTC/直连 = {total_p_input/total_d_input:.2f}x)")
        print(f"  全局耗时: 直连 {total_d_time:.1f}s vs PTC {total_p_time:.1f}s (PTC/直连 = {total_p_time/total_d_time:.2f}x)")

        if total_p_input < total_d_input:
            pct = (1 - total_p_input / total_d_input) * 100
            print(f"\n  ✅ PTC 模式平均节省 {pct:.1f}% 输入 token")
        else:
            pct = (total_p_input / total_d_input - 1) * 100
            print(f"\n  ❌ PTC 模式平均多消耗 {pct:.1f}% 输入 token")

        if total_p_time < total_d_time:
            pct = (1 - total_p_time / total_d_time) * 100
            print(f"  ✅ PTC 模式平均快 {pct:.1f}%")
        else:
            pct = (total_p_time / total_d_time - 1) * 100
            print(f"  ⚠️  PTC 模式平均慢 {pct:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
