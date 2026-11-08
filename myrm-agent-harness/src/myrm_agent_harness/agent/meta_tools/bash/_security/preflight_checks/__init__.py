"""bash 命令预检门面。

[OUTPUT]
各预检函数与共享常量。

[POS]
`..._security.preflight_checks` 的唯一入口；实现按检查族分层。
"""

from __future__ import annotations

from .background import (
    check_unquoted_background_ampersand,
)
from .destructive import (
    check_destructive_commands,
    evaluate_high_impact_command,
)
from .interactive import (
    check_interactive_command,
)
from .packages import (
    check_install_packages,
)
from .tool_guard import (
    _MAX_REFERENCED_PY_SCAN_BYTES,
    check_myrm_tools_import,
)
from .url_guard import (
    check_command_url_exfiltration,
)

__all__ = [
    "check_myrm_tools_import",
    "_MAX_REFERENCED_PY_SCAN_BYTES",
    "check_command_url_exfiltration",
    "check_destructive_commands",
    "evaluate_high_impact_command",
    "check_interactive_command",
    "check_install_packages",
    "check_unquoted_background_ampersand",
]
