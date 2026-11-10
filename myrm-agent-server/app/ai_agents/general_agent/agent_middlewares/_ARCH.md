# general_agent/agent_middlewares

## Overview

GeneralAgent-specific middleware. Injects citation rules and tool selection strategies during agent execution.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `citation_rules_middleware.py` | Core | Shows the citation formatting rules as a transient runtime HumanMessage (request.override, never stored) once the current user turn holds UNTRUSTED external sources: the notice stands right behind the tool results that first brought a source into the turn, on that request and on every later one, so each request of a run extends the one before it and the provider's cached prefix, with the signed reasoning written under it, stays valid; skips naked/search modes; adds the task integrity reminder and takes the rules' language from `prompt_locale`. | ✅ |
| `tool_selection_middleware.py` | Core | Tool constraint middleware — enforces tool_choice state machine (L2 constraint) with convergence protection for request_answer_user_tool. | ✅ |
