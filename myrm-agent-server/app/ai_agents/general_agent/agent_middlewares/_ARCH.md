# general_agent/agent_middlewares

## Overview

GeneralAgent-specific middleware. Injects citation rules and tool selection strategies during agent execution.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `citation_rules_middleware.py` | Core | Injects citation formatting rules via transient HumanMessage (request.override, cache-safe) during final_answer phase. | ✅ |
| `tool_selection_middleware.py` | Core | Tool constraint middleware — enforces tool_choice state machine (L2 constraint) with convergence protection for request_answer_user_tool. | ✅ |
