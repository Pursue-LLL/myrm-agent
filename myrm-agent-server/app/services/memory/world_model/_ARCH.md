# L3 World Model Business Service Architecture

## 1. 模块定位
`app/services/memory/world_model` 属于业务服务层（`myrm-agent-server`），负责衔接底层 Harness 宏观世界模型引擎（`L3WorldModelEngine`）与本地工作区文件系统探针。

## 2. 核心职责
- **本地工作区环境自感知**：通过 `ProjectEnvironmentProbe` 快速嗅探工作区的 `pyproject.toml`、`package.json` 及架构文档，生成多语言运行时与工程约束基线。
- **一站式宏观上下文装配**：提供 `query_macro_context`，一次性获取当前项目的四维宏观实体（安全刚性约束、环境基准、架构契约、领域模型），以防伪隔离块形式直接供 LLM System Prompt 置顶注入。
- **增量更新与状态同步**：支持前端或工作流通过 API 主动同步工作区环境（`sync_workspace_environment`）或针对单维度进行增量维护（`update_dimension`）。

## 3. 依赖关系
- `myrm_agent_harness.toolkits.memory`: 底层实体模型与渲染引擎（单向依赖）
- `app.schemas.world_model`: Pydantic V2 请求与响应 DTO
