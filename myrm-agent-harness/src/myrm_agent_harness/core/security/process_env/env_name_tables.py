"""The variable names that decide what a child process may inherit.

[INPUT]
- none (imports no other project module)

[OUTPUT]
- DEFAULT_CHILD_SAFE_ENV_KEYS: The system and toolchain names the CORE policy keeps.
- FORBIDDEN_EXACT_KEYS: The names no child environment carries.
- SENSITIVE_WILDCARDS: The substrings of the uppercase name that mark a secret.
- DANGEROUS_PREFIXES: The prefixes of names that inject code or re-route telemetry.
- PTC_ORCHESTRATION_ENV_KEYS: The internal PTC RPC bridge names, the one thing let through unfiltered.

[POS]
The name tables behind env_isolation: which variable a child process may inherit is decided by these names and by the
inherit policy applied to them there.
"""

from __future__ import annotations

from typing import Final

# Core system and development toolchain environment keys safe for child execution.
# Covers standard OS navigation, terminal display, temp storage, and language runtime paths.
DEFAULT_CHILD_SAFE_ENV_KEYS: Final[frozenset[str]] = frozenset(
    {
        # 1. POSIX & Standard Shell Core
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PATH",
        "PWD",
        "OLDPWD",
        "SHLVL",
        "LINES",
        "COLUMNS",
        "HOSTNAME",
        "HOSTTYPE",
        "MACHTYPE",
        "OSTYPE",
        "EDITOR",
        "VISUAL",
        "PAGER",
        # 2. Locale & Encoding
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_COLLATE",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_MONETARY",
        # 3. Terminal & Color
        "TERM",
        "COLORTERM",
        "FORCE_COLOR",
        "NO_COLOR",
        "TERM_PROGRAM",
        "TERM_PROGRAM_VERSION",
        # 4. Temporary Directories
        "TMPDIR",
        "TMP",
        "TEMP",
        # 5. Windows System Core
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "COMMONPROGRAMFILES",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "ALLUSERSPROFILE",
        "PUBLIC",
        # 6. XDG Base Directory Specification
        "XDG_RUNTIME_DIR",
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_DATA_DIRS",
        "XDG_CONFIG_DIRS",
        # 7. Common Language Runtimes & Package Managers (paths/flags only, no secrets)
        "GOPATH",
        "GOROOT",
        "GOBIN",
        "CARGO_HOME",
        "RUSTUP_HOME",
        "NVM_DIR",
        "NODE_PATH",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
        "CI",
        "DEBIAN_FRONTEND",
        # 8. Git Author & Committer Identity (non-sensitive developer metadata)
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
        # 9. Proxy & Ephemeral Egress Routing
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        # 12. Safe User Defined Testing Variables
        "SAFE_SYSTEM_VAR",
    }
)

# High-risk exact keys strictly forbidden in child environments
FORBIDDEN_EXACT_KEYS: Final[frozenset[str]] = frozenset(
    {
        # Noise protocol tokens & Codex execution server credentials
        "NOISE_AUTH_TOKEN",
        "NOISE_PRIVATE_KEY",
        "NOISE_REMOTE_PUB",
        "NOISE_HANDSHAKE_TOKEN",
        "CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN",
        "OPENAI_IDENTITY_TOKEN_FILE",
        "OPENAI_FEDERATION_RULE_ID",
        # Vault and master encryption keys & Myrm control plane tokens
        "MYRM_VAULT_MASTER_KEY",
        "CREDENTIAL_VAULT_KEY",
        "VAULT_TOKEN",
        "VAULT_MASTER_KEY",
        "MYRM_AGENT_SERVER_TOKEN",
        "MYRM_CONTROL_PLANE_TOKEN",
        "MYRM_AUTH_TOKEN",
        # Privileged agent sockets & admin configurations
        "SSH_AUTH_SOCK",
        "GPG_AGENT_INFO",
        "KUBECONFIG",
        "DOCKER_CONFIG",
        "NETRC",
        # Databases & storage connection strings with embedded credentials
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_PASSWORD",
        "DB_PASSWORD",
        "REDIS_URL",
        "REDIS_PRIVATE_URL",
        "REDIS_PASSWORD",
        "PGPASSWORD",
        "PGPASS",
        "AMQP_URL",
        "MONGO_URL",
        # Tokens & HTTP auth headers
        "AUTH_TOKEN",
        "ACCESS_TOKEN",
        "REFRESH_TOKEN",
        "SESSION_TOKEN",
        "JWT_SECRET",
        "SESSION_SECRET",
        "BEARER_TOKEN",
        "AUTHORIZATION",
        "HTTP_AUTHORIZATION",
        "COOKIE",
        "HTTP_COOKIE",
        # Dynamic linker & runtime injection vectors
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "LD_AUDIT",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "DYLD_FRAMEWORK_PATH",
        "NODE_OPTIONS",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONPATH",
        "SSLKEYLOGFILE",
    }
)

# Substrings / wildcards indicating secrets (checked against uppercase key)
SENSITIVE_WILDCARDS: Final[tuple[str, ...]] = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH_",
    "_AUTH",
    "AUTHORIZATION",
    "AUTHENTICATION",
    "BEARER",
    "PRIVATE",
    "SIGNATURE",
    "PASS",
)

# Prefixes that inject code into a child or re-route its telemetry: dynamic linker / loader hooks, and
# OpenTelemetry configuration. ``OTEL_EXPORTER_OTLP_*`` holds the operator's collector endpoint and its
# credentials, and downstream redaction does not recognise the URL-encoded (``%20``) header form that the
# OTLP specification prescribes, so a model-run program must never inherit them. A program that needs
# OpenTelemetry sets ``OTEL_*`` inline on its own command line.
DANGEROUS_PREFIXES: Final[tuple[str, ...]] = (
    "LD_",
    "DYLD_",
    "GIT_SSL_",
    "OTEL_",
)

# Controlled internal PTC RPC bridge variables
PTC_ORCHESTRATION_ENV_KEYS: Final[frozenset[str]] = frozenset(
    {
        "_MYRM_PTC_SOCKET",
        "_MYRM_PTC_PORT",
        "_MYRM_PTC_TIMEOUT",
    }
)
