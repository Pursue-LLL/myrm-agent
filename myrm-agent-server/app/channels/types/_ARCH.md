# types/

## Overview
Channel system domain types — pure data definitions, no I/O.

Detailed design: [REPLY_CONTEXT_DESIGN.md](REPLY_CONTEXT_DESIGN.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Channel system domain types — pure data definitions, no I/O. | — |
| components.py | Core | UI component type definitions. Cross-channel interactive component abstractions for buttons, quick r | ✅ |
| messages.py | Core | Core message type definitions. All cross-channel communication data structures | ✅ |
| notification.py | Core | Channel notification mode enum, notify/guest/explicit-mention metadata keys, and `with_final_notify` helper. | ✅ |
| session.py | Core | Session identity and policy definitions. Provides session-isolated key generation | ✅ |
| status.py | Core | Channel status, StartMode, and diagnostic type definitions. Used for Gateway health checks and startup strategy. | ✅ |
| thread_sharing.py | Core | Thread sharing mode enumeration for topic-level session isolation. | ✅ |
