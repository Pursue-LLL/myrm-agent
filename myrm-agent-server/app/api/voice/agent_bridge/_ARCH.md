# app/api/voice/agent_bridge 子包架构

语音会话的 STT→Agent 桥。`VoiceAgentBridge` 是一个持有会话状态的 dataclass，行为按职责拆成四个 mixin；`app.api.voice.agent_bridge` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `VoiceAgentBridge`、`_extract_speakable_segments` / `_log_turn_latency` 等测试与调用方使用的符号 | — |
| `common.py` | 辅助 | `_TranscriptEntry`、logger 与全部语音常量（句末正则、transcript 上限、Supervisor 超时、中英文提示文案、打断 TTL） | ✅ |
| `bridge.py` | 核心 | `@dataclass VoiceAgentBridge(TurnMixin, StreamMixin, ParamsMixin, TtsMixin)`：会话状态字段（ws、config、agent/chat id、锁、取消令牌、transcript、TTS 事件） | ✅ |
| `turn.py` | 核心 | `handle_stt_final`（一轮语音：取消旧回合 → 跑 Agent → TTS）、`_cancel_current_turn`、`_handle_approval_required`、`_send_json`、延迟日志 | ✅ |
| `streams.py` | 核心 | Fast-Lane 判定与消费、带监督的 Agent 流消费（超时移交后台）、后台交接、可朗读片段切分 | ✅ |
| `params.py` | 核心 | `_build_agent_params`：为语音回合构造 `GeneralAgentParams`（profile、安全覆盖、web fetch 门控、模型 rebuild） | ✅ |
| `tts.py` | 核心 | TTS 分段流式发送、工作中提示、兜底播报、`cancel_tts` 与打断闩锁 | ✅ |

## 依赖关系

- 上游：`myrm_agent_harness.utils.runtime.cancellation`、`app.ai_agents`（`GeneralAgentParams`）、`app.channels.types`（`VoiceConfig`）、FastAPI `WebSocket`
- 下游：`app/api/voice/realtime.py` 等语音入口、`tests/api/voice`
