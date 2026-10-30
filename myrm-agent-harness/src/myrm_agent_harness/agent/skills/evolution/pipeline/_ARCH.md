# pipeline/

## Overview
Agent Skills Evolution Pipeline module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| frustration_detector.py | Core | Frustration signal detector. Zero-LLM regex detection of user style/format/workflow frustration signals (中英双语). The server's frustration routing (`frustration_routing.py` in the general agent) calls it after a finished turn and hands the extracted preference to the skill growth review as a skill patch draft; the evolution engine is not involved. | ✅ |
| patch.py | Core | Patch application system for skill evolution. | ✅ |
| screener.py | Core | Evolution screening pipeline. Implements multi-phase checks including static error interception, GUI-First force retry, and LLM confirmation. LLM confirmation JSON parsed via `parse_llm_json_object` (robust against fences, prose, trailing commas). The `EvolutionStrategy` gate runs first: balanced and innovate let every evolution type through, repair-only lets only FIX through; innovate also overrides an LLM rejection whose confidence is below 0.7. The lock gate follows: the store's flag rejects without reading the skill, then `skill_from_disk` merges the SKILL.md frontmatter lock, so a lock written into the file only (a new skill carries it there) rejects too; the cooldown and the LLM confirmation then work from the SKILL.md text, not the stored copy. | ✅ |
| trace_analyzer.py | Core | Trace Analyzer for Skill Evolution. `extract_trajectory` builds the English failure report a FIX repair prompt carries (session overview, failure mode, tool stats, clustered errors, run totals, recent tool events) and returns an empty string when the log holds no events for the session, so `SkillEvolutionEngine.fix_skill` keeps its plain error text. A chat's log holds every turn of the chat and a limited read returns the first events, so the report reads the end of the log: the last 20 failures and the last 5 tool events come from one unlimited read of the tool events. The report never repeats the skill text: the generator and the judge each receive it whole. The session id is the name of the event log file, which for a chat is the chat id. The failure-mode scan reads `tool_timeout` / `tool_failure`; a query for a type the logger never writes returns nothing and raises nothing, so `tests/architecture/test_event_queries_name_written_types.py` checks every `event_types=` literal. Includes `_extract_takeover_evidence()` to surface human takeover demonstrations as supplementary context for LLM-driven fixes. `SkillEvolutionEngine` creates it only when `EvolutionIntegration` is given an `event_log_backend`; the server runtime passes a read-only `FileEventLogBackend` on the agents' event log directory. Every event the prompt text is built from passes `_redacted`, which applies `sanitize_event_data` again after the list is cut to the events the report shows (the redaction costs about half a millisecond an event): the log is the record and may predate a rule, and an error, a takeover URL or an ARIA tree must not reach the model as stored. The tool names that `extract_trajectory` prints come from the summary helpers, which return the log as stored, and a badly written call is kept whole in that field: they go through `_stored_tool_name`. Any other text those helpers return must be redacted the same way before it enters the prompt. | ✅ |
| variant_generator.py | Core | Variant Generator with modular prompt assembly (editing principles, hard constraints, conservative editing, failure attribution, preference embedding, gene bank prior injection). Supports FIX/DERIVED content variants and preference-driven DERIVED variants. A content prompt holds the whole skill: a cut would make the model rewrite only the part it saw and drop the rest. | ✅ |

## Key Dependencies

- `backends`
- `utils`
