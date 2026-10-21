# app/config/subagents/custom


---

## 架构概述

用户自定义子 Agent 类型的 **YAML 数据目录**。将 `example.yaml.template` 复制为 `*.yaml` 并按约定填写；`tools` 名必须在 `tool_layers._TOOL_LAYERS` 注册，否则加载失败。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `example.yaml.template` | 示例 | 自定义 YAML 模板 |
