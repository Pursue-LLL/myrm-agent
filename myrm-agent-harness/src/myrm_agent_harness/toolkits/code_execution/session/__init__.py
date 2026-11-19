"""Persistent Session Module

Provides persistent shell sessions: one long-running shell that serves the commands of a conversation.

Features:
- The session's configured environment variables and the ``sticky`` settings of a command stay in the shell
- A POSIX command runs in a child process of the shell, so the directory, variables, functions and aliases it
  changes die with it
- Session isolation (per chat_id)
- Commands of one session run one at a time; a shell that died is rebuilt by the next command
- Health check
- Performance optimization (20-100x improvement)

Notes:
- Python variables do NOT persist (each execution is isolated)
- Use filesystem to pass data between executions
"""

from myrm_agent_harness.toolkits.code_execution.session.local_session import (
    LocalPersistentSession,
    create_persistent_session,
)
from myrm_agent_harness.toolkits.code_execution.session.models import (
    SessionConfig,
    SessionExecutionResult,
)
from myrm_agent_harness.toolkits.code_execution.session.persistent_session import PersistentSession
from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import (
    ShellFlavor,
)
from myrm_agent_harness.toolkits.code_execution.session.stream_output_processor import (
    StreamOutputProcessor,
)

__all__ = [
    "LocalPersistentSession",
    "PersistentSession",
    "SessionConfig",
    "SessionExecutionResult",
    "ShellFlavor",
    "StreamOutputProcessor",
    "create_persistent_session",
]
