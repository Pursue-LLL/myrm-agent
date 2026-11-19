# market/

## Overview
External marketplace skill install meta-tool (LLM-facing name: `skill_market_tool`; actions: `search`, `install`, `install_from_url`). The host (the product layer) builds it with `create_skill_market_tool` and mounts it on Turn 1 when `enable_skill_market` is ON, passing it through `tools=`; neither `get_meta_tools` nor `SkillAgent` creates it.

**Boundary**: searches and installs from **external sources** (GitHub, skills.sh, etc.). For skills already bound to the agent, use `skill_search_tool` + `skill_select_tool` instead.

**Host contract**: the description and the install result send the model to the skill catalog and the built-in `skill_select_tool`. An agent running with `no_builtin_tools` gets neither, so its host leaves this tool unmounted.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill market meta-tool. | — |
| skill_market_tool.py | Core | Skill market meta-tool (LLM name: `skill_market_tool`). | ✅ |

## Key Dependencies

- `backends`
