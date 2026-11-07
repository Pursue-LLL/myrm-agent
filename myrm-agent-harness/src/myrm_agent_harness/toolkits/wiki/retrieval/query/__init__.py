"""[INPUT]
- .base::SemanticSearchFn (POS: 语义检索函数签名)
- .engine::WikiQueryEngine (POS: 查询入口)

[OUTPUT]
- WikiQueryEngine / SemanticSearchFn

[POS]
`myrm_agent_harness.toolkits.wiki.retrieval.query` 的唯一门面；实现按检索/加载/答案/编排分层。
"""

from myrm_agent_harness.toolkits.wiki.retrieval.query.base import SemanticSearchFn
from myrm_agent_harness.toolkits.wiki.retrieval.query.engine import WikiQueryEngine

__all__ = ["SemanticSearchFn", "WikiQueryEngine"]
