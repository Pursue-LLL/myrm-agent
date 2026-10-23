# app/config/subagents — Subagent YAML 配置

> 业务层子 Agent 类型 YAML（built-in 在 `core/`，自定义在 `custom/`）。**唯一配置来源**：各 YAML 文件的 `config:` 块。

## Architecture

- **Framework** (`myrm-agent-harness`): `load_subagent_configs_from_directory()` 纯函数加载
- **Business** (`myrm-agent-server`): 本目录 YAML 内容 + `subagent_presets.py` 注册

## Directory Structure

```
app/config/subagents/
├── _ARCH.md
├── core/          # adversarial-reviewer.yaml, browser.yaml, structure-planner.yaml,
│   │              # layout-designer.yaml, format-verifier.yaml, explore.yaml
│   │              # （完整清单见 core/_ARCH.md）
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
name: structure-planner   # 必须与文件名一致
description: "..."
tools: [file_read_tool, grep_tool, glob_tool]
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
- `explore.yaml` — read-only `file_read_tool`, `grep_tool`, `glob_tool`
- `structure-planner.yaml` / `layout-designer.yaml` / `format-verifier.yaml` — office deliverable specialists used by the prebuilt Office Full-Chain Delivery agent

## Registration

`app/ai_agents/subagent_presets.py::register_default_subagent_configs()` 在启动时加载并注册。
