# services/memory/extract_retry 模块架构

## 架构概述

记忆提取失败持久化重试队列（幂等入队 + 退避重试 + 重启恢复 + 终态账本）。后台 worker（lifespan 管理）启动即扫描、每 60s 扫描与 `wake()` 即时唤醒；对指定 chat 最近一轮重新调度 `auto_extract_memories`，与 agent run 路径一致的隐私保护上下文重建。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `extract_retry_queue.py` | 核心 | 记忆提取持久化重试队列（SQLite 表 `memory_extract_retries`）。幂等入队/原子领取(attempt 自增)/成功删除/失败指数退避与终态 failed/聊天删除级联清理；单进程语义，重启由启动扫描恢复 | ✅ |
| `extract_retry_worker.py` | 核心 | 记忆提取重试后台 worker（lifespan 管理）。启动即扫描（重启恢复）+ 每 60s 扫描 + `wake()` 即时唤醒（手动重试/observer 入队后立即扫描，sweep 期间到达的 wake 不丢失）；`asyncio.timeout(240s)` 包裹提取；失败按退避重试至 `MAX_ATTEMPTS` 后写 ERROR 账本事件 | ✅ |
| `retry_chat_memory_extract.py` | 核心 | 对指定 chat 最近一轮 user/assistant 重新调度 `auto_extract_memories`；`ContextAssemblyService.resolve_binding_for_chat` + dedup_llm · incognito 拒绝 · 持久化队列幂等入队（`scheduled`/`already_in_flight`）· 重试仅压缩轨（`enable_verbatim=False` 防 verbatim 重复写入）；`run_retry_extract_for_chat` 供 worker 与手动共用（source 区分 `worker_retry_extract`/`manual_retry_extract`）；用户开启隐私保护时在任务内重建 harness privacy 上下文（policy + PseudonymStore + regex PII 假名化闭包三件套），`privacyDeepScan` 时叠加 LLM 深度扫描，与 agent run 路径完全一致；非法 PII action 值回退默认避免任务崩溃 | ✅ |
