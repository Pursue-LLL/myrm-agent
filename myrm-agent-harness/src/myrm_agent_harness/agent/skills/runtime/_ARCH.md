# runtime/

## Overview

Skill execution runtime: registry, command path utilities, trust attenuation. **`get_metadata_summary()`** builds XML for the HumanMessage catalog blocks — the `<bound_skills>` baseline and the `<bound_skills_update>` tail (see `skill_catalog_delivery.py` and `meta_tools/skills/select/_ARCH.md`).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Runtime — skill execution runtime. | — |
| attenuator.py | Core | Trust attenuator. Three-layer filtering; `allowed_tools` narrows only by names that are registered or bound (names from other skill ecosystems are ignored and warned once per skill; a skill with no recognized name does not narrow). Model-layer restriction via `middlewares/_skill_tool_choice.py` + `SkillAttenuationMiddleware`. Execution fallback: `check_trust_attenuation`. | ✅ |
| session_skills_rehydrate.py | Core | Rebuild `loaded_skills` from chat history ∪ `context.session_loaded_skill_names` SSOT at `SkillAgent.run()` start. Each recorded name resolves through `resolve_skill_reference` against the bound skills (a spelling such as the `_skill`-suffixed runtime name still finds its skill; an ambiguous or unknown name restores nothing), and a skill recorded under two spellings is restored once, under the name the catalog lists. | ✅ |
| command_paths.py | Core | Skill command path utilities: rewrite `.claude/skills/` paths to relative, detect skill script commands in bash execution. | ✅ |
| skill_invocation.py | Core | Calling convention of a skill's scripts, one rule for what the executor accepts and what the model is told. `plain_skill_call` lexes the command line (`core/security/shell_command_lexer`) and names the skill only when every command of the line is `[interpreter [bare flags]] .claude/skills/<name>/<file> args` of one skill (redirections allowed); a path inside a comment or an operand, a pipe or chain to another program, `cd`, command or process substitution, a subshell, `bash -c`, an assignment prefix, an expansion, `..`, or a second skill is not a plain call. `skill_call_notice` is the quoted block the skill loader puts under a skill document's title; `settings_withheld_note` is what a failed command is told when the skill's saved settings were held back. | ✅ |
| registry.py | Core | SkillRegistry (`register`, `get_skill`, `get_mcp_skill_for_ipc` backed by `_ipc_mcp_skill_cache` so parent PTC IPC calls survive subagent `clear_mcp_skills()` passes) + `get_metadata_summary` (XML for HumanMessage catalog; generic selection rules live in `skill_select_tool.description`; L1 emits the hidden/search dynamic rules when any skill is hidden, followed by one `<hidden_skill_names>` line: every model-visible skill without an inline entry, alphabetical, within `L1_HIDDEN_NAMES_MAX_TOKENS` and closed by an `and N more not listed` note when a very large library overflows it). | ✅ |
| catalog_display.py | Core | resolve_catalog_display_skills + should_mount_skill_search_tool SSOT for runtime, `get_meta_tools` and the server's config preview. Who earns a full entry: a non-empty `skill_configs` → the explicit `is_core` flag, else the skill's own `always`; `None` and `{}` are one unconfigured state in which every model-visible skill is a candidate. Candidates run `always` first, then by name, into the L1 token budget; everything else is hidden (named in the catalog) and `overflow_count` says how many candidates the budget left out. | ✅ |
| skill_catalog_delivery.py | Core | Frozen baseline plus tail updates: `<bound_skills hash hidden_count>` (hash over the rendered body, hidden names included) is written once on the first HumanMessage of a (re)built conversation and never rewritten; on drift `<bound_skills_update hash>` carries the full current list on the new HumanMessage and supersedes earlier lists (`empty` hash announces no skills). What a thread last delivered is read from the thread's own messages (`last_delivered_catalog_key`), so a compaction that drops the blocks makes the next turn deliver the list again. Delivery flow lives in `agent/_internals/skill_catalog_turn.py`. | ✅ |

## Key Dependencies

- `backends.skills` (SkillMetadata)
- `core.security.shell_command_lexer` (`plain_skill_call`: the one reading of a shell command line)
- `agent.tool_management.tool_layers` (`is_registered_action_tool`: Action Tool name SSOT for `allowed_tools` recognition)
