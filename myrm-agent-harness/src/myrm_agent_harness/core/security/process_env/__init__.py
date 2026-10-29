"""Public facade for the environment of the processes the framework starts.

[INPUT]
- code_injection_env::CODE_INJECTION_ENV_VARS, CODE_INJECTION_ENV_PREFIXES, is_code_injection_env_name (POS: Names that make a program run what the value names)
- env_isolation::EnvInheritPolicy, DEFAULT_CHILD_SAFE_ENV_KEYS, FORBIDDEN_EXACT_KEYS, build_isolated_child_env, sanitize_env, is_non_inheritable_env_var (POS: What a child process inherits)

[OUTPUT]
- CODE_INJECTION_ENV_VARS / CODE_INJECTION_ENV_PREFIXES / is_code_injection_env_name — the names no credential, export or child environment may carry
- EnvInheritPolicy / build_isolated_child_env / sanitize_env / is_non_inheritable_env_var / DEFAULT_CHILD_SAFE_ENV_KEYS / FORBIDDEN_EXACT_KEYS — the environment a child process gets

[POS]
Public facade of the process-environment domain.
"""

from .code_injection_env import (
    CODE_INJECTION_ENV_PREFIXES,
    CODE_INJECTION_ENV_VARS,
    is_code_injection_env_name,
)
from .env_isolation import (
    DEFAULT_CHILD_SAFE_ENV_KEYS,
    FORBIDDEN_EXACT_KEYS,
    EnvInheritPolicy,
    build_isolated_child_env,
    is_non_inheritable_env_var,
    sanitize_env,
)

__all__ = [
    "CODE_INJECTION_ENV_PREFIXES",
    "CODE_INJECTION_ENV_VARS",
    "DEFAULT_CHILD_SAFE_ENV_KEYS",
    "FORBIDDEN_EXACT_KEYS",
    "EnvInheritPolicy",
    "build_isolated_child_env",
    "is_code_injection_env_name",
    "is_non_inheritable_env_var",
    "sanitize_env",
]
