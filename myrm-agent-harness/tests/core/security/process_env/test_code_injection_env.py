"""The environment variable names that make a program run what their value names.

``BASH_ENV`` and ``GIT_EXTERNAL_DIFF`` make a later ``bash -c`` or ``git diff`` run a script, so no credential and no
child environment may carry them; proxies, TLS and package sources only redirect traffic and stay settable.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.process_env import (
    CODE_INJECTION_ENV_VARS,
    DEFAULT_CHILD_SAFE_ENV_KEYS,
    is_code_injection_env_name,
)
from myrm_agent_harness.toolkits.code_execution.security.blacklist import (
    DANGEROUS_ENV_PREFIXES,
    DANGEROUS_ENV_VARS,
)


class TestCodeInjectionEnvNames:
    def test_injection_names_are_a_part_of_the_dangerous_ones(self) -> None:
        assert CODE_INJECTION_ENV_VARS < DANGEROUS_ENV_VARS

    def test_the_hosts_blacklist_keeps_every_injection_name_and_the_redirection_ones(self) -> None:
        assert {"LD_PRELOAD", "BASH_ENV", "NODE_OPTIONS", "PYTHONPATH", "PERL5OPT", "RUBYOPT"} <= DANGEROUS_ENV_VARS
        assert {"HTTP_PROXY", "SSL_CERT_FILE", "PIP_INDEX_URL", "CC", "ENV", "IFS"} <= DANGEROUS_ENV_VARS
        assert set(DANGEROUS_ENV_PREFIXES) == {"LD_", "DYLD_", "GIT_SSL_"}

    def test_a_name_a_shell_commonly_sets_is_not_an_injection_name(self) -> None:
        assert not (CODE_INJECTION_ENV_VARS & DEFAULT_CHILD_SAFE_ENV_KEYS)
        for name in ("CC", "CXX", "ENV", "IFS", "HTTP_PROXY", "PIP_INDEX_URL", "PAGER", "EDITOR", "PATH"):
            assert not is_code_injection_env_name(name), name

    @pytest.mark.parametrize("name", ["bash_env", "Git_External_Diff", "LD_ANYTHING", "dyld_whatever", "LD_"])
    def test_names_are_matched_without_regard_to_case_and_by_family(self, name: str) -> None:
        assert is_code_injection_env_name(name)

    @pytest.mark.parametrize("name", ["", "OLD_PRELOAD", "BASH_ENVIRON", "GIT_DIR", "FIELD_X"])
    def test_longer_or_unrelated_names_are_not_matched(self, name: str) -> None:
        assert not is_code_injection_env_name(name)
