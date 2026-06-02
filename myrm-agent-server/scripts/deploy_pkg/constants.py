from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_LOCAL = PROJECT_ROOT / ".env.local"

ENV_SANDBOX = PROJECT_ROOT / ".env.sandbox"

ENV_FILE = PROJECT_ROOT / ".env"

ENV_DEFAULTS = PROJECT_ROOT / ".env.defaults"

ENV_SECRETS = PROJECT_ROOT / ".env.secrets"

ENV_SECRETS_EXAMPLE = PROJECT_ROOT / ".env.secrets.example"

POSTGRES_USER = "myrmagent"

POSTGRES_PASSWORD = "myrmagent"

POSTGRES_DB = "myrmagent"

