"""The shell that reads a background command follows the platform, not the name ``sh``."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._executor.background_mixin import _background_shell
from myrm_agent_harness.toolkits.code_execution.platform import ShellType, detect_platform

_DETECT_PLATFORM = "myrm_agent_harness.agent.meta_tools.bash._executor.background_mixin.detect_platform"


def test_a_host_with_bash_reads_a_job_with_the_path_of_its_bash() -> None:
    host = replace(detect_platform(), shell_type="bash", shell_path="/opt/bash/bin/bash")

    with patch(_DETECT_PLATFORM, return_value=host):
        assert _background_shell() == "/opt/bash/bin/bash"


@pytest.mark.parametrize("shell_type", ["powershell", "cmd"])
def test_a_host_without_bash_reads_a_job_with_the_sh_on_its_path(shell_type: ShellType) -> None:
    host = replace(detect_platform(), shell_type=shell_type, shell_path="C:/shell/host.exe")

    with patch(_DETECT_PLATFORM, return_value=host):
        assert _background_shell() == "sh"
