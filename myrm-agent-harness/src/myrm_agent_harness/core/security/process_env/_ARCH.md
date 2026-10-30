# core/security/process_env/

## Overview

What a process the framework starts may inherit and what may be set for it: one definition of the variable names that make a program run foreign code (read by every check that must refuse them) and the one construction of a child process environment.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public facade: `CODE_INJECTION_ENV_VARS`, `CODE_INJECTION_ENV_PREFIXES`, `is_code_injection_env_name`, `EnvInheritPolicy`, `DEFAULT_CHILD_SAFE_ENV_KEYS`, `FORBIDDEN_EXACT_KEYS`, `build_isolated_child_env`, `sanitize_env`, `is_non_inheritable_env_var`. | ✅ |
| `code_injection_env.py` | Core | The names that make a later program run what the value names: the dynamic linker (`LD_*`, `DYLD_*`), language runtimes (`PYTHONPATH`, `NODE_OPTIONS`, `RUBYOPT`, ...), shell startup (`BASH_ENV`) and git program hooks (`GIT_SSH_COMMAND`, `GIT_EXTERNAL_DIFF`, ...). Proxy, TLS and package-source names are not in it: they redirect traffic and a person may set them. | ✅ |
| `env_isolation.py` | Core | The child-process environment, built from a policy (`EnvInheritPolicy`: `CORE` keeps only proven-safe system and toolchain variables, `ALL` keeps the rest minus sensitive ones, `NONE` starts empty). Sensitive names and patterns, linker/loader hooks (`LD_*`, `DYLD_*`), `GIT_SSL_*` and OpenTelemetry configuration (`OTEL_*`) are stripped under every policy, explicit overrides included; `is_non_inheritable_env_var` is the post-override scrub. | ✅ |

## Key Dependencies

- Standard library only.

## Consumers

- `core/security/ephemeral_credentials/types.py` — `validate_credential_key` refuses these names for a one-command credential, so a staged credential cannot make a command judged read-only run a program.
- `toolkits/code_execution/security/blacklist.py` — `DANGEROUS_ENV_VARS` / `DANGEROUS_ENV_PREFIXES` are built from them.
- `toolkits/code_execution/security/persistent_env.py` — an `export` of one of them into the persistent shell is blocked.
- `toolkits/code_execution/executors/local/*`, `toolkits/code_execution/session/local_session.py`, `toolkits/browser/pool/browser_launch_env.py`, `toolkits/acp/runtime/_base.py`, `toolkits/computer_use/backends/cua_driver/backend.py`, `agent/hooks/executor.py`, `core/security/safe_exec.py` — `sanitize_env` / `build_isolated_child_env` build the environment a child process gets.
