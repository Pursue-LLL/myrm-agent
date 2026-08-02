# browser_domain_skills/

## Overview

REST API layer for managing browser domain executable skills.
Delegates to harness-layer `DomainSkillStore` for storage and matching.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports router | ✅ |
| router.py | Core | CRUD endpoints: list, get, delete, distill; is_builtin detection; tool_name path-safety validation | ✅ |

## Key Dependencies

- `myrm_agent_harness.toolkits.browser.domain_skills` — `DomainSkillStore` singleton
