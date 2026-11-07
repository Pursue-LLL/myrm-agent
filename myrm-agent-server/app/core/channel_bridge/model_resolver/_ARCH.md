# app/core/channel_bridge/model_resolver 子包架构

模型配置解析、自定义定价注册与能力/上下文窗口增强。纯函数、无模块级可变状态；按解析阶段拆成 4 个模块，`app.core.channel_bridge.model_resolver` 导入路径不变（含被外部直接引用的私有 helper）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 导出原 `__all__` 的 8 个名字 + 现有调用方/测试直接引用的 helper（`_build_platform_headers`、`_normalize_model_name`、`_resolve_override` 等） | — |
| `common.py` | 辅助 | 平台/传输 header 构建、API key 提取（含 loopback / platform-managed 判定）、`provider/model` 名称转换、重复前缀折叠与模型名归一、provider 类型映射、常量 | — |
| `resolve.py` | 核心 | `resolve_model_config`（用户默认回退 + override 解析）、`validate_model_override`、`_fallback_model_from_providers`、`_resolve_override` | — |
| `pricing.py` | 核心 | `register_custom_model_pricing`：把用户自定义成本登记进模型目录（`register_model`；用户明确填写的窗口才登记） | — |
| `enrich.py` | 核心 | `enrich_model_capabilities` / `enrich_model_context_window` 及其 customModelInfo / 模型目录（`model_facts`）查询 helper，窗口与视觉能力不虚构默认值 | — |

## 依赖方向

`common`（叶子）← `resolve` / `pricing` / `enrich`；三者之间零交叉依赖，`__init__` 只做聚合。

## 依赖关系

- 上游：harness `agent.config.parsers`（`to_route_model_id` / `parse_route_model_id`）、`toolkits.llms.catalog`（`model_facts` / `register_model`）、`app.core.wire.enrich`
- 下游：`app/services/agent/params/**`、`app/core/channel_bridge/config_*`、`app/api/agents/**`、`app/services/chat/**`、`app/services/kanban/**`
