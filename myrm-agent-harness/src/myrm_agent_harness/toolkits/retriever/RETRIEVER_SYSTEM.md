# 检索系统设计文档

> 框架：`myrm_agent_harness.toolkits.retriever`

---

## 一、设计目标

构建 **混合检索** 的 RAG 检索系统：

- **语义 + 关键词**：向量搜索（语义）与 BM25（关键词）结合，提高召回率
- **灵活管道**：预处理 → 分块 → 嵌入 → 并行检索 → 融合 → 重排序
- **可插拔**：嵌入模型与融合策略可替换；向量检索是纯内存的 numpy 实现，不依赖外部向量库
- **性能优化**：智能缓存、批量处理、并发检索、性能监控

---

## 二、系统架构

### 2.1 检索管道

```
1. 文档预处理 (preprocessing)  — 过滤、清理、标准化
2. 文档分块 (splitter)         — 长文档分割，多种分块策略
3. 文本嵌入 (embedding)        — 本地/云端嵌入服务
4. 并行检索 (vector + BM25)    — 向量语义 + 关键词检索
5. 结果融合 (fusion_strategies)— RRF、加权等融合策略
6. 重排序 (reranker)           — 精排提升相关性
7. 返回 Top-K 结果
```

### 2.2 模块依赖关系

```
hybrid_retriever (混合检索器)
  ↓ 使用
├─ vector_search/ (向量检索)
│   ↓ 使用
│   embedding/ (嵌入服务)
├─ bm25_retrieval (关键词检索)
│   ↓ 使用
│   bm25/ (BM25 算法)
└─ reranker/ (重排序)
```

### 2.3 子模块职责

| 子模块 | 职责 |
|--------|------|
| **embedding/** | 文本嵌入（本地/云端），支持多种嵌入模型 |
| **bm25/** | BM25 算法实现、分词器与 IDF 区分度词项选择 |
| **reranker/** | 检索结果重排序（提高相关性） |
| **splitter/** | 文档分块（多种分块策略） |
| **preprocessing/** | 文档预处理（过滤、清理、标准化） |
| **hybrid_search/** | 混合搜索管道（检索 → 融合 → 重排序） |
| **sufficiency/** | 检索充分性评估（LLM-based 后检索质量判断 + 负面约束检测） |
| **vector_search/** | 向量搜索（纯内存 numpy 实现） |
| **cjk_tokenizer** | 确定性单趟保序 CJK/ASCII 分词与两档检索规划（无 C 扩展依赖） |

### 2.4 仓库内的调用方

`RetrieverManager`（`engine.py`）服务于 `web_fetch` 的 `fetch_and_extract`：抓取页面、分块后，按问题取最相关的片段。分块数不超过 `hybrid_top_k_per_query`（默认 50）时直接重排；超过时先用 BM25 + 向量检索缩小范围，再重排。网页搜索（`web_search/`）把各搜索服务返回的结果直接合并，不调用 `RetrieverManager`。

---

## 三、融合策略

`fusion_strategies.py` 提供：

- **`rrf_fusion`**：倒数排名融合（RRF），支持列表级权重；混合检索里 BM25 与向量两路结果用它合并
- **`fuse_rrf_deterministic`**：带多级平局裁决与分数归一化的确定性 RRF，同时返回逐来源的召回调试信息
- **`unified_fusion`**：四柱正交融合（质量、优势、共识、声望），合并多个查询的重排结果。`FusionPipeline` 与 `RetrieverManager` 的默认权重是 `(1, 0, 0, 0)`，即每篇文档的得分取它在所有查询里的最高重排分；其余三柱要调用方显式传入权重才生效
- **自定义**：在 `fusion_strategies` 中扩展

---

## 四、与 app/core/retriever 的关系

- **myrm_agent_harness.toolkits.retriever**：通用检索框架，零业务依赖
- **app.core.retriever**：业务层封装，集成知识库、权限、图存储等

---

## 五、相关文档

- [ARCHITECTURE.md](../../../../ARCHITECTURE.md) - 项目整体架构
- `embedding/` - 嵌入服务模块
- `bm25/` - BM25 实现模块
- `reranker/` - 重排序服务模块
