"""Public facade for the environment of the processes the framework starts.

[INPUT]
- code_injection_env::CODE_INJECTION_ENV_VARS, CODE_INJECTION_ENV_PREFIXES, is_code_injection_env_name (POS: Names that make a program run what the value names)

[OUTPUT]
- CODE_INJECTION_ENV_VARS / CODE_INJECTION_ENV_PREFIXES / is_code_injection_env_name — the names no credential, export or child environment may carry

[POS]
Public facade of the process-environment domain.
"""

from .code_injection_env import (
    CODE_INJECTION_ENV_PREFIXES,
    CODE_INJECTION_ENV_VARS,
    is_code_injection_env_name,
)

__all__ = [
    "CODE_INJECTION_ENV_PREFIXES",
    "CODE_INJECTION_ENV_VARS",
    "is_code_injection_env_name",
]
