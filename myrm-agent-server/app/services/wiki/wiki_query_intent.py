"""Deterministic gate for Chat Wiki Knowledge Quick Lane.

[INPUT]
- app.services.agent.params.helpers::_extract_text_from_query
- app.services.agent.stream_session.stream_session_types::AgentStreamSession

[OUTPUT]
- should_use_wiki_knowledge_lane(): strict eligibility for zero-LLM wiki lane

[POS]
Business-layer intent classifier — no LLM gate; prefer false negatives over misroutes.
"""

from __future__ import annotations

import re

from app.services.agent.params import MultimodalQuery, _extract_text_from_query
from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.wiki.vault import is_vault_ready, vault_has_wiki_content

_MAX_QUESTION_CHARS = 800

_QUESTION_MARK_RE = re.compile(r"[?？]\s*$")
_QUESTION_HINT_RE = re.compile(
    r"(?i)(?:"
    r"what|when|where|who|why|how|which|how many|how much|"
    r"多少|几个|几条|几种|哪位|哪些|哪次|何时|何地|为何|为什么|是不是|是否|"
    r"什么|啥|咋|怎样|如何|有没有|能否|可不可以"
    r")"
)
_NUMERIC_QUERY_RE = re.compile(
    r"(?i)(?:"
    r"count|total|sum|average|percentage|ratio|"
    r"统计|总数|合计|占比|比例|数量"
    r")"
)

_IMPERATIVE_PREFIX_RE = re.compile(
    r"(?i)^(?:"
    r"please\s+)?(?:"
    r"run|execute|compile|maintain|apply|ingest|import|delete|remove|create|write|update|sync|publish|open|browse|search the web|"
    r"请?(?:运行|执行|编译|维护|应用|导入|入库|删除|移除|创建|写入|更新|同步|发布|打开|浏览|抓取|入库)"
    r")\b"
)

_IMPERATIVE_ANYWHERE_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:wiki_ingest|wiki_apply|wiki_compile|wiki_maintain)\b|"
    r"(?:导入|入库|编译|lint|维护)\s*(?:wiki|知识库|vault)?|"
    r"(?:ingest|compile|maintain)\s+(?:wiki|vault|this|the)\b"
    r")"
)


def _query_has_non_text_parts(query: MultimodalQuery) -> bool:
    if isinstance(query, str):
        return False
    for part in query:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type not in (None, "text"):
            return True
    return False


def matches_wiki_query_intent(question: str) -> bool:
    """Return True when the utterance looks like a read-only wiki knowledge question."""
    text = question.strip()
    if not text or len(text) > _MAX_QUESTION_CHARS:
        return False
    if _IMPERATIVE_PREFIX_RE.search(text):
        return False
    if _IMPERATIVE_ANYWHERE_RE.search(text):
        return False
    if _QUESTION_MARK_RE.search(text):
        return True
    if _QUESTION_HINT_RE.search(text):
        return True
    if _NUMERIC_QUERY_RE.search(text):
        return True
    return False


def should_use_wiki_knowledge_lane(session: AgentStreamSession) -> bool:
    """Strict eligibility for Chat Wiki Knowledge Lane (zero-LLM retrieval)."""
    request = session.request
    params = session.params

    if request.action_mode != "agent":
        return False
    if not params.enable_wiki or params.incognito_mode or request.incognito_mode:
        return False
    if request.use_workflow or request.resume_value is not None or request.workflow_template_id:
        return False
    if request.blueprint_id or request.ephemeral_subagents:
        return False
    if request.mention_references:
        return False
    if request.uploaded_file_ids:
        return False
    if _query_has_non_text_parts(request.query):
        return False

    question = _extract_text_from_query(request.query).strip()
    if not question:
        return False
    if not matches_wiki_query_intent(question):
        return False

    agent_id = params.agent_id or request.agent_id
    shared_context_ids: list[str] | None = params.memory_shared_context_ids or getattr(
        request, "session_knowledge_base_ids", None
    )
    if not is_vault_ready(agent_id, shared_context_ids=shared_context_ids):
        return False
    if not vault_has_wiki_content(agent_id, shared_context_ids=shared_context_ids):
        return False
    return True
