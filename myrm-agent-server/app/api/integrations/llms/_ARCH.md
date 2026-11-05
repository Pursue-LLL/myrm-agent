# app/api/integrations/llms 子包架构

LLM 集成的探测类端点。按探测区域分模块，共用一个 `APIRouter`，`__init__.py` 作为聚合出口（路由与测试只依赖它）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `router` 与全部端点/模型/内部 helper（保持 `app.api.integrations.llms` 导入路径） | — |
| `common.py` | 辅助 | `router` / `logger`、本地免密 marker、`_apply_local_no_auth_marker_transport_overrides` | ✅ |
| `discovery.py` | 核心 | `discover-models`：URL 规范化、候选端点推导、SSRF 白名单（loopback / RFC1918 / Tailscale CGNAT / `.local` 分机） | ✅ |
| `verify.py` | 核心 | `verify` 与 `check-reachability`：真实上游探针（每次直接问提供方，传输层不保存应答）、OAuth marker、可达性缓存（30 秒，键含模型/端点/Key 摘要） | ✅ |
| `model_info.py` | 核心 | `model-info` / `model-info/batch`：按 `model_facts` 查模型目录（大小写不敏感；经网关的复合名取其背后的模型）、能力构建、按名检索候选（跳过已过 `deprecation_date` 的模型） | ✅ |
| `speed_test.py` | 核心 | `speed-test`：批量测速与首字延迟排序 | ✅ |
| `preflight.py` | 核心 | `model-switch-preflight`：目标模型上下文窗口解析（前端传入值优先，其次目录里的 `max_input_tokens`，没有就是未知）与压缩估算 | ✅ |

## 依赖关系

- 上游：harness `secure_request` / `create_httpx_client` / SSRF guard、`app.core.utils.chat_utils`、`app.core.utils.errors`、`app.schemas.responses`
- 下游：`app.api.integrations.router`（挂载 `router`）、设置页前端、`tests/api/integrations`
