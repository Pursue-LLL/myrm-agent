# api/config/

## 架构概述

Omni-Config 读写与预检 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 配置管理 API | ✅ |
| `artifact_mappings.py` | 模块 | 工件类型映射 API 端点 | ✅ |
| `router.py` | 路由 | 配置服务 API 路由层。处理 HTTP 请求，进行 Pre-flight Validation 强类型校验；`searchServices` 保存前执行 legacy role→priority 迁移并校验 manifest slug、enabled selectable、priority 唯一。浏览器 hot-reload 经 `get_configured_browser_pool()` 初始化 pool。包含 Telegram onboarding 原子编排端点（凭据校验 + DM 策略 + 默认 Agent 绑定 + 失败回滚 + 同名 Agent 确定性复用 + 进程内锁 + 基于 state_dir 的跨进程 FileLock 防重，避免并发冲突导致重复创建；锁占用返回 `409 + TELEGRAM_ONBOARDING_IN_PROGRESS` 语义供前端无感重试）。**Second Brain preset**：`GET/POST /onboarding/second-brain/{status,apply}` — 复用 `second_brain_assistant` 模板 + `read_it_later` + `wiki_morning_delta` blueprint + default vault seed；apply 成功 message 含 seed 文件计数；status 发现 preset agent 已删则清 config；apply 带 FileLock 409；持久化 `secondBrainPreset` checklist。**Vision health**：`POST /vision-health` — `extract_vision_fallback_model_config` 判定是否配置；`build_vision_fallback_engine_from_providers` 构建完整 failover 链并对 1×1 PNG 做 `describe_image_b64` 探活；失败字符串或异常时 `healthy=false`；成功时返回配置 primary `model` 与实际 `resolved_model`（failover 成功且与 primary 不同时）；Settings「Test vision chain」按钮消费。**Video health**：`POST /video-health` — `extract_video_fallback_model_config` + `build_video_fallback_probe_engine_from_providers` 对 video 链做 1×1 PNG 连通性探活；Settings「Test video chain」按钮消费。 | ✅ |
