# api/config/

## 架构概述

Omni-Config 读写与预检 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 配置管理 API | ✅ |
| `artifact_mappings.py` | 模块 | 工件类型映射 API 端点 | ✅ |
| `router.py` | 路由 | 组合根：按原路径顺序挂载 `routes/` 下的域路由（catalog/onboarding/media_health/crud/diagnostics）与 pricing/privacy-preview；`GET /config` 根路径保留在此 | ✅ |
| `routes/` | 子包 | 配置 API 域路由：catalog（schema/全量/就绪）、onboarding（引导/Second Brain/SearXNG）、media_health（视觉/视频）、crud（单键 CRUD/历史/回滚/同步）、diagnostics（本地模型/代理自检）、support（锁与写入前校验）；详见 [routes/_ARCH.md](routes/_ARCH.md) | ✅ |
| `pricing.py` | 路由 | 模型四维单价矩阵与 Prompt Cache 经济学数据只读查询 API。提供 `GET /model-pricing`，从 LiteLLM 权威数据提取以 $/1M tokens 计价的输入、输出、Cache 读写单价及节省率。 | ✅ |
| `privacy_preview.py` | 路由 | 隐私保护「试一试」：`POST /privacy-preview` 接收一句话与表单里的处理方式、自定义规则（字段与对话请求同名），经 harness `preview_privacy_policy` 返回识别级别、处理方式、模型实际会收到的文本（被拦截时为 null）与无法生效的自定义模式 `ineffective_patterns`（句子可为空：有规则时无需等用户输入句子即可查询）。规则随请求而来、不读不写已保存设置、不落日志；仅正则层，不含深度扫描；同步路由，伪匿名化时用一次性临时存储，不触碰真实假名映射。 | ✅ |
