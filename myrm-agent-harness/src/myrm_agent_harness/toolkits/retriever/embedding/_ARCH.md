# embedding/

## Overview
Embedding Service Toolkit.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Embedding 模块门面入口：导出 `EmbeddingService` 与工厂方法 | ✅ |
| base.py | Core | Embedding contract layer. Declares the abstract interface that every embedding backend | ✅ |
| cloud_embedding.py | Core | Cloud embedding backend. Translates EmbeddingService into embedding API calls with auto batch splitting (count + chars dual protection; a provider's per-request token cap is spent as characters at one token per character with a 0.9 margin, e.g. Cloudflare `@cf/baai/bge-m3` 60,000 tokens -> 54,000 characters), retry, dimension detection, and embed-window preflight. Supports Ollama via api_base. The transport behind `aembed` sends `encoding_format="float"` to every provider except Voyage and Jina, which return float arrays when the field is absent | ✅ |
| window_policy.py | Core | EmbedWindowPolicy SSOT: model max input tokens (looked up by model id; an id missing from the table gets the conservative 512 default, so each provider-specific id of a known model needs its own row, e.g. SiliconFlow `BAAI/bge-m3` and Cloudflare Workers AI `@cf/baai/bge-m3`), effective chunk budget, EmbedInputTooLargeError, token_counter_for_model（wordpiece 家族 bge/bce/nomic/minilm/e5/gte/paraphrase/jina→estimate、BPE→o200k 统一计数出口） | ✅ |
| factory.py | Core | Embedding factory. CloudEmbedding only (api_key required). Process-wide singleton | ✅ |

## Tests

| File | Coverage |
|------|----------|
| `tests/toolkits/retriever/test_embed_window_policy.py` | window_policy/embed_budget 100%、vector_chunks 100%；bge-m3 在 SiliconFlow（`BAAI/bge-m3`）与 Cloudflare Workers AI（`@cf/baai/bge-m3`）两种 id 下窗口都是 8192、分块预算都是 7372 |
| `tests/toolkits/retriever/test_cloud_embedding_batch_split.py` | 批拆分按条数与字符数两个上限贪心装包；Cloudflare `bge-m3`（`@cf/baai/bge-m3` 与 `openai/@cf/baai/bge-m3` 两种 id）每个请求的字符数不超过其 60,000 token 上限的 0.9，其它模型仍按 100,000 字符装包 |
| `tests/toolkits/retriever/test_cloud_embedding_dimension.py` | 已知模型维度表对各种 id 写法的解析（含 `BAAI/bge-m3`、`@cf/baai/bge-m3`）；表里没有的 id 要到首次嵌入调用后才知道维度 |
| `tests/toolkits/retriever/test_cloud_embedding_request_params.py` | CloudEmbedding 经传输层发出的嵌入请求：Voyage 与 Jina 不带 `encoding_format`，OpenAI 系与 OpenAI 兼容端点带 `float`，Cohere 为 `embedding_types=["float"]`，带自定义 `api_base` 的 Voyage 型号按 OpenAI 兼容网关处理（整个模型名加 `float`），空白文本以一个空格占位 |
| `myrm-agent-server/tests/api/integrations/test_embedding_provider_wire_contract.py` | 真实 CloudEmbedding 与传输层打到回环假上游，断言各服务商线上收到的嵌入请求体（Voyage 与 Jina 无 `encoding_format`、OpenAI 系与自定义端点上的 Voyage 型号带 `float`、Cohere `embedding_types=["float"]`；服务商经各自的端点变量到达回环） |
| `tests/integration/test_embed_window_real_embedding_integration.py` | 真实 HTTP 全链路 10 例（wordpiece 字符预算 / BPE token 预算 / 小窗口 0.5 margin / 韩文不超窗 / 中英韩混合 / 超窗 fail-loud / memory 截断 / wiki ingest，关键路径零 mock；本地 OpenAI 兼容端点返回确定性哈希向量，只验证预算、窗口与传输，不验证嵌入质量，同时打通产品自托管 api_base 用法） |
