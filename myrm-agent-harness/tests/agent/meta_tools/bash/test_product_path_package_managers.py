"""Package-manager commands through the real bash tool and a real shell.

The header the tool puts in front of every command wraps ``npm`` and its relatives. A stand-in ``npm`` on the PATH
records how it was called, so these cases show what the wrapper hands to the tool the model asked for, and what it
leaves in the caller's shell, without a network or a registry.
"""

from __future__ import annotations

import sys

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack, StubBin

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_TIMEOUT = 20


async def test_npm_install_reaches_npm_with_every_argument(real_stack: RealBashStack, stub_bin: StubBin) -> None:
    stub_bin.add("npm", 'echo "npm-called: $*"')

    output = await real_stack.run("npm install left-pad@1.3.0 --no-save", timeout=_TIMEOUT)

    assert output.count("npm-called: install left-pad@1.3.0 --no-save") == 1


async def test_a_failing_npm_install_fails_the_command_instead_of_being_retried(
    real_stack: RealBashStack, stub_bin: StubBin
) -> None:
    stub_bin.add("npm", 'echo "npm-called: $*"\necho "npm ERR! boom" >&2\nexit 3')

    output = await real_stack.run("npm install", timeout=_TIMEOUT)

    assert output.count("npm-called:") == 1
    assert "npm ERR! boom" in output
    assert "[exit_code: 3]" in output
    assert "Fallback" not in output


async def test_a_package_manager_call_leaves_the_variables_of_the_caller_alone(
    real_stack: RealBashStack, stub_bin: StubBin
) -> None:
    stub_bin.add("npm", "exit 0")

    output = await real_stack.run("arg=mine\nnpm --version\necho arg=$arg", timeout=_TIMEOUT)

    assert "arg=mine" in output
