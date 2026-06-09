# utils 模块架构


---

## 架构概述

业务特有工具函数模块，提供错误处理、响应格式化、文件操作、聊天格式转换、图片压缩等核心能力。是整个系统的通用工具层，被各模块广泛使用。专注通用性和可复用性。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `errors.py` | 核心 | `MyrmError`、`StandardHTTPException`、`register_exception_handlers`、HTTP 异常快捷函数（validation/not_found/auth/permission/conflict/internal/service_unavailable/external）和 LLM/embedding 依赖错误分类。开发模式（DEBUG=true）下错误响应包含完整堆栈追踪。注：`ToolError` 由框架层提供（`myrm_agent_harness.utils.errors`） | — |
| `response_utils.py` | 核心 | `success_response`、`list_response`、`paginated_response` | — |
| `files_utils.py` | 核心 | `extract_file_id_from_url`、`read_image_as_base64`（通过 FilesService + StorageProvider 统一存储访问） | — |
| `chat_utils.py` | 核心 | `ChatHistoryReq`/`ChatHistory`、`convert_chat_history`（前端 → LangChain）、`_process_human_content`/`_process_image_item`（图像自适应降级路由 Vision Fallback，使用辅助 vision model 将图片转文本，并通过 SSE 发送 analyzing_image 状态事件；包含 Reactive Compress 逻辑，大图自动压缩后传输） | — |
| `image_compressor.py` | 核心 | `ImageCompressor`：压缩、尺寸调整、格式转换、Base64 | — |
| `network.py` | 核心 | `get_local_ip`：获取本机局域网 IP（WebUI 二维码、启动地址打印） | — |
| `delivery_provenance.py` | 核心 | Human 前缀投递横幅：`format_delivery_banner`、`prepend_plain_banner`、`ingress_from_channel_metadata`、`apply_delivery_banner`、`resolve_general_agent_pipeline_labels`（含 `web_chat`→http_gui/browser_sse、`cron`、`eval`、**`headless_wakeup`→async_wake_consumer** 等）、`apply_general_agent_pipeline_banner`；多模态首块合并且幂等 | ✅ I/O/P 见文件头 |
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | — |

---

## 依赖关系

- **内部**：`fastapi`、`PIL`、`langchain_core`、`app/database`（standard_responses）
- **被依赖**：`app/api/`、`app/services/`、`app/ai_agents/`、`app/core/*`
