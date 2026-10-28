# core/security/process_env/

## Overview

What a process the framework starts may inherit and what may be set for it. One definition of the variable names that make a program run foreign code, read by every check that must refuse them.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public facade: `CODE_INJECTION_ENV_VARS`, `CODE_INJECTION_ENV_PREFIXES`, `is_code_injection_env_name`. | ✅ |
| `code_injection_env.py` | Core | The names that make a later program run what the value names: the dynamic linker (`LD_*`, `DYLD_*`), language runtimes (`PYTHONPATH`, `NODE_OPTIONS`, `RUBYOPT`, ...), shell startup (`BASH_ENV`) and git program hooks (`GIT_SSH_COMMAND`, `GIT_EXTERNAL_DIFF`, ...). Proxy, TLS and package-source names are not in it: they redirect traffic and a person may set them. | ✅ |

## Key Dependencies

- Standard library only.

## Consumers

- `core/security/ephemeral_credentials/types.py` — `validate_credential_key` refuses these names for a one-command credential, so a staged credential cannot make a command judged read-only run a program.
- `toolkits/code_execution/security/blacklist.py` — `DANGEROUS_ENV_VARS` / `DANGEROUS_ENV_PREFIXES` are built from them.
- `toolkits/code_execution/security/persistent_env.py` — an `export` of one of them into the persistent shell is blocked.
