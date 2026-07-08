# app/config/subagents — Subagent YAML 配置

> 业务层子 Agent 类型 YAML（built-in 在 `core/`，自定义在 `custom/`）。**唯一配置来源**：各 YAML 文件的 `config:` 块。

## Architecture

- **Framework** (`myrm-agent-harness`): `load_subagent_configs_from_directory()` 纯函数加载
- **Business** (`myrm-agent-server`): 本目录 YAML 内容 + `subagent_presets.py` 注册

## Directory Structure

```
app/config/subagents/
├── _ARCH.md
├── core/          # adversarial-reviewer.yaml, analysis.yaml, browser.yaml, coding.yaml, deep-audit.yaml, search.yaml
└── custom/        # 用户覆盖（example.yaml.template）
```

## Configuration Priority

1. `custom/*.yaml` 覆盖同名 `core/*.yaml`
2. 每个文件内 `config:` 块定义运行时参数（timeout、max_turns 等）
3. 未写字段时使用 harness `config_loader` 内置默认（120/25/5/3）

**无 env 层、无全局 policy 层。**

## YAML Format

Tool names in `tools` / `disallowed_tools` must match `@tool()` names registered in harness `tool_layers._TOOL_LAYERS` (validated at load time).

```yaml
name: search   # 必须与文件名一致
description: "..."
tools: [web_search_tool, web_fetch_tool]
system_prompt: |
  ...
config:
  timeout_seconds: 30
  concurrency_limit: 10
  max_turns: 3
  max_retries: 1
```

Core presets (SSOT tool names):
- `browser.yaml` — eight `browser_*_tool` entries; pair with prebuilt `browser-automation` skill when browser is enabled
- `analysis.yaml` — `memory_recall_tool`, `memory_save_tool`, `memory_manage_tool`
- `search.yaml` — `web_search_tool`, `web_fetch_tool`

## Registration

`app/ai_agents/subagent_presets.py::register_default_subagent_configs()` 在启动时加载并注册。
