# Co-Pilot (Lean v1)

Business-layer Run Observer + Session Advisor. Side Q&A does not enter the main agent transcript.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `run_digest_store.py` | 核心 | Process-local RunDigest SSOT；stream progress + approval pending 同步；SSE `run_digest_updated` | ✅ |
| `advisor_service.py` | 核心 | Tier-0 状态 regex + Tier-1 lite model 只读问答；`Accept-Language` → locale | ✅ |
| `advisor_thread_store.py` | 辅助 | 旁路线程内存存储（每 chat 最多 50 条） | ✅ |

## 依赖

- Harness DTO：`myrm_agent_harness.agent.streaming.run_digest` (POS: 纯 reducer，无 I/O)
- Stream hook：`app/services/agent/streaming_support/stream_collector.py::_sync_run_digest`
- Approval hook：`app/services/approvals/registry.py::_sync_copilot_pending`
- API：`app/api/chats/chat/copilot.py`
