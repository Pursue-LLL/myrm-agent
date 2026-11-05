"""English LLM-facing static texts for memory_save_tool and memory_manage_tool.

[INPUT]
(none: static text only)

[OUTPUT]
- MEMORY_SAVE_CORE_EN: memory_save_tool description core (English)
- MEMORY_MANAGE_TOOL_DESCRIPTION_EN: memory_manage_tool description (English)

[POS]
English half of the memory tool description SSOT; composed by ``_memory_agent_tool_descriptions``.
"""

MEMORY_SAVE_CORE_EN = """Store a new memory for the user. Memory persists across sessions and is injected into future conversations, so keep entries compact and focused on durable facts: one standalone declarative fact per entry.

**WHEN TO SAVE** (do this proactively):
- User explicitly says "remember this", "note this", "don't forget"
- User corrects your behavior or output style (agent conduct — not a stored fact correction; see below)
- User shares a stable preference, habit, or personal detail (name, role, timezone)
- You discover something about the user's environment or project that won't change soon
- User sets a rule: "always do X" / "never do Y"

**WHEN NOT TO USE THIS TOOL**:
- An existing recalled memory fact is wrong → use memory_manage_tool with action=correct (do not save a duplicate)
- Task progress, session outcomes, or completed-work logs → use memory_search_tool with corpus=sessions
- Temporary state: PR numbers, commit SHAs, current file paths, WIP items
- Real-time business states: order/logistics tracking, live account balances, OTP/verification codes, temporary download or queue links — query live integrations instead
- Information that will be stale within a week
- Step-by-step procedures or workflows (not suitable for memory)
- Raw data dumps, code snippets, or lengthy text
- Do not retry identical content if the tool reports a duplicate

**CONTENT QUALITY** — write as declarative facts, not instructions:
- GOOD: "User prefers dark themes" (declarative fact)
- BAD: "Always use dark theme" (instruction-style, gets misinterpreted as a command)
- One fact per memory entry; include enough context to be useful standalone

**ATTRIBUTION & TRANSIENT STATES** (CRITICAL):
- Strictly distinguish the user from third parties (family, friends, colleagues). NEVER attribute a third party's traits, illnesses, or preferences to the user (e.g., "User's boss prefers dark mode", NOT "User prefers dark mode").
- DO NOT save transient emotional or psychological states (e.g., "User is feeling anxious today") unless explicitly stated as a chronic condition.

**CATEGORY GUIDE** (pick one):
- knowledge: stable facts about user's world (project tech stack, environment details) — tags and importance apply here
- event: significant past occurrences worth recalling (e.g., user started new project) — do not specify importance or tags for events
- preference: user likes/dislikes (requires preference_key)
- rule: conditional behavioral rules with a specific condition (requires rule_trigger, e.g., "when writing code"; optional rule_priority, rule_keywords)
- instruction: unconditional global rules that always apply (e.g., "always reply in Chinese") — do not set rule_trigger
- pitfall: failed attempts, bugs, or dead-ends to prevent repeating (requires failure_reason and negative_lesson; optional subtask_phase)

**IMPORTANCE SCORING** (0–1, primarily for knowledge):
- 0.8–1.0: User explicitly asked to remember / correction of your behavior
- 0.5–0.7: Inferred stable preference or environment fact
- 0.2–0.4: Supplementary context, nice-to-have

**WRITE TARGET**:
- "bound" (default): visible only to the current agent persona
- "shared": cross-agent knowledge (user's name, timezone) — use sparingly

Parameter semantics are in the tool schema."""

MEMORY_MANAGE_TOOL_DESCRIPTION_EN = """Update, delete, correct, or rate an existing memory from memory_search_tool results.

**WHEN TO USE** (not memory_save_tool):
- User says "forget that", "that's wrong", or "remove that memory"
- A recalled memory is outdated or inaccurate → correct
- A memory needs minor wording fix or weight change → update
- User confirms a memory was helpful → rate (reinforces retrieval ranking)

**WHEN NOT TO USE**:
- Storing new facts, preferences, or rules → memory_save_tool
- Task progress or chat history → memory_search_tool with corpus=sessions

**ACTION GUIDE**:
- delete: remove a memory (memories the user protected cannot be deleted by the agent)
- update: tweak wording or importance only — fact remains true (e.g., fix typo "Pyhton" -> "Python"); requires new_content; a memory the user protected cannot be updated by the agent — ask the user to release the protection first
- correct: replace an outdated or wrong fact with the new truth (e.g., "User lives in Beijing" -> "User moved to Shanghai") — knowledge category only; requires new_content; preserves history; use instead of memory_save_tool when correcting existing memories; a memory the user protected cannot be corrected by the agent — ask the user to release the protection first
- rate: record user feedback — knowledge or event only; requires rating_score 1-5 (1=poor, 5=excellent)

**CATEGORY LIMITS**:
- correct → knowledge only
- rate → knowledge or event only
- preference profile attributes cannot be deleted via this tool
- instruction saves (via memory_save_tool) are stored as rules; manage them with category=rule

Parameter semantics are in the tool schema."""
