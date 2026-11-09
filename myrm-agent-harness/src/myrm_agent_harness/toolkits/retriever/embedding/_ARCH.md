# embedding/

## Overview
Embedding Service Toolkit.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Embedding 模块门面入口：导出 `EmbeddingService` 与工厂方法 | ✅ |
| base.py | Core | Embedding contract layer. Declares the abstract interface that every embedding backend | ✅ |
| cloud_embedding.py | Core | Cloud embedding backend. Translates EmbeddingService into embedding API calls with auto batch splitting (count + chars dual protection), retry, dimension detection, and embed-window preflight. Supports Ollama via api_base. The transport behind `aembed` sends `encoding_format="float"` to every provider except Voyage and Jina, which return float arrays when the field is absent | ✅ |
    | window_policy.py | Core | EmbedWindowPolicy SSOT: model max input tokens, effective chunk budget, EmbedInputTooLargeError, token_counter_for_model（wordpiece 家族 bge/bce/nomic/minilm/e5/gte/paraphrase/jina→estimate、BPE→o200k 统一计数出口） | ✅ |
| factory.py | Core | Embedding factory. CloudEmbedding only (api_key required). Process-wide singleton | ✅ |

## Tests

| File | Coverage |
|------|----------|
| `tests/toolkits/retriever/test_embed_window_policy.py` | window_policy/embed_budget 100%、vector_chunks 100% |
| `tests/toolkits/retriever/test_cloud_embedding_request_params.py` | CloudEmbedding 经传输层发出的嵌入请求：Voyage 与 Jina 不带 `encoding_format`，OpenAI 系与 OpenAI 兼容端点带 `float`，Cohere 为 `embedding_types=["float"]`，带自定义 `api_base` 的 Voyage 型号按 OpenAI 兼容网关处理（整个模型名加 `float`），空白文本以一个空格占位 |
| `myrm-agent-server/tests/api/integrations/test_embedding_provider_wire_contract.py` | 真实 CloudEmbedding 与传输层打到回环假上游，断言各服务商线上收到的嵌入请求体（Voyage 与 Jina 无 `encoding_format`、OpenAI 系与自定义端点上的 Voyage 型号带 `float`、Cohere `embedding_types=["float"]`；服务商经各自的端点变量到达回环） |
| `tests/integration/test_embed_window_real_embedding_integration.py` | 真实 HTTP 全链路 10 例（wordpiece 字符预算 / BPE token 预算 / 小窗口 0.5 margin / 韩文不超窗 / 中英韩混合 / 超窗 fail-loud / memory 截断 / wiki ingest，关键路径零 mock，本地 OpenAI 兼容端点打通产品自托管 api_base 用法） |
