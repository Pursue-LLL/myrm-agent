# Evidence Playback Service Architecture

记忆证据链溯源、上下文切片回放与脱敏服务。

## 模块定位与职责

桥接底层对话流水表（`Message` / `ChannelMessageModel`）与前端 Memory Command Center 证据回放抽屉：
- 零大模型开销（0 LLM Calls），通过标准数据库索引秒级抓取记忆触发点的上下文切片；
- 严格敏感信息脱敏，在回放渲染前统一经过敏感凭据过滤器；
- 支撑用户在可视化记忆看板中一键溯源“为什么智能体会形成该偏好或记忆”。

## 核心组件

- `playback_service.py`：`EvidencePlaybackService` 核心实现，提供 `get_evidence_playback` 接口，支持前后上下文窗口切片与会话穿透回放。
