"""Process-wide one-time work the first agent assembly would otherwise do inline.

[INPUT]
- utils.text_utils::preheat_tiktoken (POS: Loads the token vocabulary token counting needs)
- toolkits.code_execution.env_probe::warm_up_environment_probe (POS: Builds the Python toolchain line of the bash tool description)

[OUTPUT]
- start_one_time_work: Starts both on background threads, without waiting

[POS]
Called first thing by ``create_skill_agent``. Neither job needs anything the assembly produces, so threads finish them
while the MCP servers connect; the first reader of each result finds it built or waits for the build already running,
instead of building it while the event loop stands still.
"""

from __future__ import annotations

import threading
from functools import cache


@cache
def _start_token_vocabulary() -> None:
    """Load the token vocabulary on a thread; once per process, since the encoding stays loaded."""
    from myrm_agent_harness.utils.text_utils import preheat_tiktoken

    threading.Thread(target=preheat_tiktoken, name="tiktoken-warm-up", daemon=True).start()


def start_one_time_work(*, shell_tools: bool) -> None:
    """Start, without waiting, what the assembly and the first model request would otherwise build inline.

    Parsing the token vocabulary takes a fraction of a second, and the probe processes behind the bash tool's
    description take as long: both ran in the event loop's thread, ahead of the first model request.

    Args:
        shell_tools: Whether the bash tool is mounted; only then is its description built from the probe line.
    """
    _start_token_vocabulary()
    if shell_tools:
        from myrm_agent_harness.toolkits.code_execution.env_probe import warm_up_environment_probe

        warm_up_environment_probe()
