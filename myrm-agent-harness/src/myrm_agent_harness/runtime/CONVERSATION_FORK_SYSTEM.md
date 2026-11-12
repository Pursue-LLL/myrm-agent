# Conversation Fork Design

## Overview

**Conversation Forking** enables users to create alternative exploration paths from any point in a conversation, preserving complete Agent state (messages + agent_state + tool outputs) at the fork point.

**Key Differentiator vs Competitors:**
- **Letta**: Copies message IDs (no agent_state)
- **Us**: Clones entire LangGraph checkpoint (full state restoration)

---

## Core Concepts

### Checkpoint-Based Fork

Instead of simple message copying, we leverage **LangGraph's checkpoint mechanism** for true state forking:

```python
# ❌ Naive approach (Letta-style)
forked_messages = copy(messages[:fork_index])

# ✅ Our approach (checkpoint-based)
checkpoint = await checkpointer.aget(config={"thread_id": source_thread_id})
await checkpointer.aput(
    config={"thread_id": target_thread_id},
    checkpoint=checkpoint,  # Full state: messages + agent_state + pending_writes
)
```

**What's Preserved:**
- ✅ Message history
- ✅ Agent internal state (langgraph `State`)
- ✅ Tool execution results (cached in checkpoint)
- ✅ System prompts & configuration

---

## Architecture

### Framework Layer (Harness)

The harness defines no fork-specific types. The Business Layer forks a conversation directly on the LangGraph
checkpointer's `aget_tuple` and `aput`.

---

### Business Layer (Server)

**Database Schema:**

```sql
CREATE TABLE conversation_forks (
    child_chat_id VARCHAR(255) PRIMARY KEY,
    parent_chat_id VARCHAR(255) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    fork_checkpoint_id VARCHAR(255),
    fork_message_index INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fork_child_to_parent ON conversation_forks(child_chat_id);
CREATE INDEX idx_fork_parent_children ON conversation_forks(parent_chat_id);
```

**Fork Record Model:** `ConversationFork` (`app/database/models/chat.py`, `child_chat_id` is the primary key, the other columns are the table above). The service layer returns two NamedTuples: `ForkCreateResult` (`success`, `new_chat_id`, `parent_chat_id`, `fork_point`, `error`) and `ForkInfoResponse` (`parent_chat_id`, `fork_point`, `children`, `root_chat_id`, `depth`).

**Design Decision: Direct Copy (not COW)**

| Approach | Query Complexity | Storage | Performance |
|----------|------------------|---------|-------------|
| **COW** (Copy-On-Write) | O(fork_depth) recursive queries | 90% savings | Variable, deep forks slow |
| **Direct Copy** | O(1) single table query | ~1% overhead | Constant, predictable |

**Choice:** Direct Copy for **predictable O(1) query performance**.

**Why?** Fork frequency is low (<5% conversations), storage overhead is negligible, but query performance directly impacts UX.

---

**Service Implementation:**

```python
# services/chat/conversation_fork_manager.py
class ConversationForkManager:
    @staticmethod
    async def fork_conversation(
        db: AsyncSession,
        parent_chat_id: str,
        message_index: int,
        new_title: str | None = None,
        fork_mode: str = "full_clone",   # or "acceptance_verifier"
        acceptance_scope: str | None = None,
    ) -> ForkCreateResult:
        """
        1. Validate the parent chat and the message_index against its active messages
        2. Create the new chat (messages + Chat metadata cloned, compacted_before_id remapped)
        3. Clone the LangGraph checkpoint at the fork point -> new thread_id
        4. Insert the conversation_forks record
        """

    @staticmethod
    async def get_fork_info(db: AsyncSession, chat_id: str) -> ForkInfoResponse:
        """parent / fork point / children / root_chat_id / depth (multi-generation lineage)"""
```

---

**API Endpoints:**

```python
# POST /api/v1/chats/{chat_id}/fork
{
    "message_index": 5,               # 0-based index, or -1 for the last message
    "new_title": "Alternative Path",  # Optional, auto-generated if omitted
    "fork_mode": "full_clone",        # or "acceptance_verifier"
    "acceptance_scope": null          # Optional, only for the acceptance audit mode
}

# Response
{
    "new_chat_id": "chat-456",
    "parent_chat_id": "chat-123",
    "fork_point": 5
}

# ---

# GET /api/v1/chats/{chat_id}/fork-info
{
    "parent_chat_id": "chat-123",  # null if not a fork
    "fork_point": 5,
    "root_chat_id": "chat-001",
    "depth": 1,
    "children": [
        {"chat_id": "chat-789", "title": "Branch A", "created_at": "2026-01-01T00:00:00Z"},
        {"chat_id": "chat-012", "title": "Branch B", "created_at": "2026-01-01T00:00:00Z"}
    ]
}
```

---

### Frontend Layer

`services/fork-api.ts` wraps both endpoints (`forkConversation`, `getForkInfo`). A fork starts from these entry points:

- the `/fork [title]` slash command (forks at the last message)
- the context usage panel and the sidebar chat history item (fork at the last message)
- the mobile chat sheet entries
- the session replay player (fork at the replayed point)

After the fork succeeds the new chat opens as a new workspace pane. There is no tree view of the fork lineage.

---

## Usage Examples

### User Scenario 1: Agent Took Wrong Tool

```
1. User asks: "Search latest AI papers"
2. Agent executes bash command (wrong!)
3. User forks from message #4 (session replay player)
4. New conversation starts from message #4
5. User re-phrases: "Use web search to find papers"
```

**Benefit:** No need to re-enter context, instant retry.

---

### User Scenario 2: Multi-Path Exploration

```
1. User: "Implement auth system"
2. Agent suggests JWT
3. User forks to explore session-based auth
4. Compares both approaches in parallel
```

**Benefit:** Compare solutions without losing original work.

---

### Developer Scenario 3: Prompt Engineering A/B Test

```
1. Developer forks conversation after message #3
2. Modifies system prompt in forked conversation
3. Continues with same user query
4. Compares agent responses
```

**Benefit:** Rapid prompt iteration without restarting.

---

## Performance Characteristics

| Operation | Complexity |
|-----------|------------|
| Fork Conversation | O(C + M) (C = checkpoint size, M = messages copied) |
| Query Fork Info | single indexed query per generation |
| List Children | O(N) (N = children) |

Per fork: one metadata row plus a full copy of the checkpoint and messages.

---

## Integration with Existing Systems

### Checkpoint Compatibility

Works seamlessly with:
- ✅ `AsyncSqliteSaver` (default, persistent on sandbox volume)
- ✅ `MemorySaver` (ephemeral / tests)
- ✅ Any LangGraph-compatible checkpointer

### Prompt Cache Interaction

**No conflict:** Forked checkpoint inherits existing cache tokens, new messages add incrementally.

```python
# Forked checkpoint at message #5
# Cache tokens: [0, 1, 2, 3, 4] (preserved)
# New message #6: Incremental cache (adds [5])
```

**Result:** 0ms cache invalidation, optimal token reuse.

---

## Future Extensibility

### Optional Enhancements (Not in MVP)

1. **Fork Quota** (Control Plane)
   - Limit forks per user (e.g., 10 forks/chat)
   - Prevents storage abuse in multi-tenant scenarios

2. **Fork Analytics**
   - Track fork success rate
   - Identify common fork points → improve agent

3. **Checkpoint Compression**
   - Compress old forks to save storage
   - Trade: query latency vs storage cost

**Decision:** Defer these until proven necessary (YAGNI principle).

---

## Implementation Checklist

**Framework Layer:**
- ✅ Design documentation (this file)

**Business Layer:**
- ✅ Database migration: `conversation_forks` table
- ✅ `ConversationFork` ORM model, `ForkCreateResult` / `ForkInfoResponse`
- ✅ `ConversationForkManager` service
- ✅ API endpoints: POST `/chats/{chat_id}/fork`, GET `/chats/{chat_id}/fork-info`
- ✅ Checkpoint clone logic

**Frontend:**
- ✅ `fork-api.ts` client and the `/fork` command
- ✅ Fork entry points: context usage panel, sidebar chat history, mobile sheet, session replay player
- ⬜ Parent link (Chat Header) and fork lineage UI

**Testing:**
- ✅ Server: `tests/services/chat/test_conversation_fork_manager.py`, `test_fork_carries_parked_pastes.py`, `test_context_branch_fork.py`
- ✅ Client: `services/__tests__/fork-api.test.ts`

---

## References

- LangGraph Checkpointer: https://langchain-ai.github.io/langgraph/concepts/persistence/
- Framework Design Principles: `/myrm-agent-harness/FRAMEWORK_DESIGN_PRINCIPLES.md`
