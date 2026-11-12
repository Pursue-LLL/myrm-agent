"""English LLM-facing static texts for memory_save_tool and memory_manage_tool.

[INPUT]
(none: static text only)

[OUTPUT]
- MEMORY_SAVE_CORE_EN: memory_save_tool description core (English)
- MEMORY_SAVE_WRITE_TARGET_EN: the write-target block of the save description, offered only under a shared-write policy
- MEMORY_MANAGE_TOOL_DESCRIPTION_EN: memory_manage_tool description (English)

[POS]
English half of the memory tool description SSOT; composed by ``_memory_agent_tool_descriptions``.
"""

MEMORY_SAVE_CORE_EN = """Store a new memory for the user. Memory persists across sessions and is injected into future conversations, so keep entries compact and focused on durable facts: one standalone declarative fact per entry.

**WHEN TO SAVE** (do this proactively):
- User says "remember this" or "don't forget", or sets a rule: "always do X" / "never do Y"
- User corrects your behavior or output style (agent conduct — not a stored fact correction; see below)
- User shares a stable preference, habit, or personal detail (name, role, timezone), or you discover a lasting fact about their environment or project

**WHEN NOT TO USE THIS TOOL**:
- An existing recalled memory fact is wrong → use memory_manage_tool with action=correct (do not save a duplicate)
- Task progress, session outcomes, completed-work logs, or temporary state (PR numbers, commit SHAs, current file paths, WIP items)
- Real-time business states: order/logistics tracking, live account balances, OTP/verification codes, temporary download or queue links — query live integrations instead
- Information that will be stale within a week
- Step-by-step procedures or workflows, raw data dumps, code snippets, or lengthy text
- Do not retry identical content if the tool reports a duplicate

**ATTRIBUTION & TRANSIENT STATES** (CRITICAL): NEVER attribute a third party's (family, friends, colleagues) traits, illnesses, or preferences to the user (e.g., "User's boss prefers dark mode", NOT "User prefers dark mode"). Do not save transient emotional states (e.g., "User is feeling anxious today") unless stated as a chronic condition.

**CATEGORY GUIDE** (pick one):
- knowledge: stable facts about user's world (project tech stack, environment details)
- event: significant past occurrences worth recalling (e.g., user started new project) — do not specify importance or tags for events
- preference: stable likes/dislikes about the user's world (favorite tools, foods, hobbies); a request about how you should write, format or behave is an instruction or rule, never a preference
- rule: conditional behavioral rules with a specific condition (requires rule_trigger, e.g., "when writing code")
- instruction: unconditional global rules that always apply (e.g., "always reply in Chinese") — do not set rule_trigger

**IMPORTANCE** (0–1, knowledge only; other categories ignore it): 0.8–1.0 the user explicitly asked to remember the fact; 0.5–0.7 an inferred stable fact; 0.2–0.4 supplementary context."""

# Appended to the save description only while the write policy allows shared writes.
MEMORY_SAVE_WRITE_TARGET_EN = """**WRITE TARGET**:
- "bound" (default): visible only to the current agent persona
- "shared": cross-agent knowledge (user's name, timezone) — use sparingly"""

MEMORY_MANAGE_TOOL_DESCRIPTION_EN = """Update, delete, correct, or rate an existing memory from memory_search_tool results.

**WHEN TO USE** (not memory_save_tool): the user says "forget that", "that's wrong", or "remove that memory"; a recalled memory is outdated or inaccurate (correct) or needs only a wording fix (update); or the user confirms it was helpful (rate: reinforces retrieval ranking).

**WHEN NOT TO USE**:
- Storing new facts, preferences, or rules → memory_save_tool
- Task progress or chat history (not memories)
- A [preference] result: a profile attribute has no manageable id — change it by saving the same preference_key again with memory_save_tool; the agent cannot delete one

**ACTION GUIDE**:
- delete: remove a memory
- update: tweak wording or importance only — fact remains true (e.g., fix typo "Pyhton" -> "Python")
- correct: replace an outdated or wrong fact with the new truth (e.g., "User lives in Beijing" -> "User moved to Shanghai") — knowledge memories only; preserves history; use instead of memory_save_tool when correcting existing memories
- rate: record user feedback — knowledge or event memories only; requires rating_score 1-5 (1=poor, 5=excellent)

A memory the user protected cannot be updated, corrected, or deleted by the agent — ask the user to release the protection first."""
