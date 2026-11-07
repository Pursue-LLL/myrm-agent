# memory_agent_tools/

## Overview

LangChain tools the agent uses to read and write memory: `memory_search_tool` (memory / wiki / sessions),
`memory_save_tool` and `memory_manage_tool`, each built by a `build_*` function bound to one `MemoryManager`.
`create_memory_tools` assembles them. Detailed design: [MEMORY_SYSTEM.md](../../MEMORY_SYSTEM.md).

## File Index

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | Facade | Public entry: `create_memory_tools`, `CATEGORY_TO_TYPE`. | ✅ |
| `factory.py` | Core | `create_memory_tools`: recall-mode gate, policy/backends defaults, tool assembly. | ✅ |
| `search_tool.py` | Core | `memory_search_tool`: corpus resolution, drill-down, profile lookup, section assembly. | ✅ |
| `search_input.py` | Core | `memory_search_input(policy)`: the search args schema derived from the corpus policy (`corpus` only when there is a choice, conversation-expansion arguments only with sessions); the ACL stays the authority for a corpus that is accepted but not offered. | ✅ |
| `save_tool.py` | Core | `memory_save_tool` + `MemorySaveInput` + `memory_save_input(policy)`: wiki/transient rejection, session buffering vs approval-queue writes per category; knowledge/event gates follow the manager's enabled types, so an embeddings-less deployment saves through the BM25 mirror; `write_target` is offered only when the policy allows shared writes, and a stray `shared` is still accepted and demoted to `bound`. | ✅ |
| `manage_tool.py` | Core | `memory_manage_tool` + `MemoryManageInput`: LangChain binding over `../memory_manage_core.py` (rate/delete/update/correct by memory id; protected memories refused). | ✅ |
| `common.py` | Util | `CATEGORY_TO_TYPE` mapping and `parse_string_list` argument normaliser. | ✅ |

## Key Dependencies

- `../memory_search_policy.py`, `../memory_search_execution.py`, `../memory_recall_*.py`, `../tool_result_sources.py`
- `../wiki_memory_boundary.py`, `../transient_fact_boundary.py`, `../write_failure_feedback.py`
- `../_memory_agent_tool_descriptions.py` (LLM-visible descriptions, injected by `factory.py`)
- `../../manager.py`, `../../session.py`, `../../types/`
