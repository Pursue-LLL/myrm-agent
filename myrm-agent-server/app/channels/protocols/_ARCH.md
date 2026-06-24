# protocols/

## Overview
Channel system protocols — interfaces for business-layer injection.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Channel system protocols — interfaces for business-layer injection. | — |
| adapters.py | Core | Adapter layer for framework independence. Business layer implements these | ✅ |
| agent.py | Core | Agent execution protocol for Channel inbound messages. Framework AgentRouter delegates via this protocol; supports cancel_token, steering_token, and topic_context. | ✅ |
| async_login.py | Core | Protocol layer for external channel async login. Enables channels to | ✅ |
| compact.py | Core | Business-layer handler protocol for the /compact slash command. Framework parses user_id | ✅ |
| goal_command.py | Core | Business-layer handler protocol for /goal slash commands. Framework parses subcommands and delegates goal lifecycle operations via this protocol. | ✅ |
| metrics.py | Core | Protocol layer for route observability. Enables business layer to | ✅ |
| pairing.py | Core | Storage protocol for Channel user identity binding and group access policies (`get_guest_mode`, enabled groups). Framework resolves inbound | ✅ |
| rate_limiter.py | Core | Protocol layer for route-level rate limiting. Enables business layer | ✅ |
| route_registrar.py | Core | Protocol layer for dynamic HTTP route registration. Enables channels to declare | ✅ |
| skill_command.py | Core | Business-layer handler protocol for skill-bound slash commands. Framework delegates /command → Skill invocations via this protocol. | ✅ |
| topic.py | Core | Topic/channel-level management protocol. Supports two binding granularities for flexible channel rou | ✅ |
| background_task.py | Core | Business-layer handler protocol for /background (/btw /bg) slash commands. Framework delegates background session lifecycle (spawn, list, cancel, steer) via this protocol. | ✅ |
| status.py | Core | Business-layer handler protocol for /status slash command. Framework provides runtime state (agent running, queue depth, yolo mode) and delegates session metadata retrieval (session_id, title, tokens, model, timestamps) via StatusProvider protocol. | ✅ |
| turn_management.py | Core | Business-layer handler protocol for /retry and /undo slash commands. | ✅ |
| kanban_command.py | Core | Business-layer handler protocol for /kanban (/kb) slash commands. Framework delegates kanban board management (list, show, create, comment, edit, complete, block, unblock, archive, stats) via this protocol. | ✅ |
| learn_command.py | Core | Business-layer handler protocol for /learn slash command. Framework delegates skill learning prompt construction via this protocol. | ✅ |

## Key Dependencies

- `utils`
