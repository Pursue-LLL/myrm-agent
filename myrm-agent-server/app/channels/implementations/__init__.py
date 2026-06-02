"""Framework-specific implementations of channel route registration.

Provides ready-to-use implementations of RouteRegistrar Protocol for
popular web frameworks (FastAPI).

[INPUT]
- channels.protocols::RouteRegistrar, (POS: Protocols for Skill Optimization Subsystem)

[OUTPUT]
- FastAPI implementation (optional dependency: pip install myrm-agent-harness[fastapi])

[POS]
Implementation layer for web framework integration. Provides out-of-the-box
implementations so users don't need to implement RouteRegistrar themselves.
Each implementation is an optional dependency to keep the core framework lightweight.
"""
