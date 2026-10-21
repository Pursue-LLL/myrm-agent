"""Declarative credential schema for channel providers.

Framework-level type definitions and resolution logic. Each Provider
declares its own ``ChannelCredentialSpec`` describing the credentials
it needs. The business layer provides a ``CredentialSource`` callback
to supply raw values (from DB, file, vault, etc.).

[INPUT]
(no external dependencies — pure data structures)

[OUTPUT]
- CredentialField: single credential field mapping (env_var + default)
- ChannelCredentialSpec: per-provider credential schema
- resolve_credentials: generic resolver using pluggable source callback
- parse_bool: str→bool converter for credential values

[POS]
Framework-level credential type definitions and generic parser. Providers declare
required credentials; business layer provides values via CredentialSource callback.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def camel_to_snake(name: str) -> str:
    """Convert a camelCase key to snake_case.

    Uses a lookbehind so consecutive capitals survive intact
    (e.g. ``baseURL`` -> ``base_url``, never ``base_u_r_l``).
    """
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def channel_credentials_config_key(
    channel_name: str,
    known_keys: Mapping[str, str] | None = None,
) -> str:
    """Resolve the UserConfig ``config_key`` for a channel or its instances.

    Default channels look up *known_keys* (e.g. ``{"wechat": "wechatCredentials"}``);
    instance channels (named ``{type}_{instance_id}``) and unknown channels
    fall back to the ``{channel_name}Credentials`` convention.

    Args:
        channel_name: Channel or instance name (e.g. ``"wechat"``, ``"wechat_a1b2c3"``).
        known_keys: Optional default-instance mapping (channel name -> config_key).

    Returns:
        The config_key used to read/write this channel's credentials in UserConfig.
    """
    if known_keys:
        mapped = known_keys.get(channel_name)
        if mapped:
            return mapped
    return f"{channel_name}Credentials"


@dataclass(frozen=True, slots=True)
class CredentialField:
    """Single credential field mapping.

    Attributes:
        db_key: Key used in the external credential store (e.g. DB column).
        env_var: Legacy name for UI/error hints (not used for credential resolution).
        default: Default value when neither source provides one.
        required: Whether this field is required (no default allowed if True).
        is_sensitive: Whether this field contains sensitive data (should be encrypted/redacted).
        help_text: Human-readable help text for UI display.
        validator: Optional function to validate/transform the value.
    """

    db_key: str
    env_var: str
    default: str = ""
    required: bool = True
    is_sensitive: bool = True
    help_text: str | None = None
    validator: Callable[[str], str] | None = None


@dataclass(frozen=True, slots=True)
class ChannelCredentialSpec:
    """Declarative credential schema for a channel provider.

    ``config_key`` identifies the credential group in the external store
    (e.g. ``"feishuCredentials"``). ``fields`` maps constructor parameter
    names to their credential sources.
    """

    config_key: str
    fields: tuple[tuple[str, CredentialField], ...]


def credential_spec(config_key: str, **fields: CredentialField) -> ChannelCredentialSpec:
    """Shorthand for constructing a frozen spec."""
    return ChannelCredentialSpec(config_key=config_key, fields=tuple(fields.items()))


def credential_field(
    db_key: str,
    env_var: str,
    default: str = "",
    required: bool = True,
    is_sensitive: bool = True,
    help_text: str | None = None,
    validator: Callable[[str], str] | None = None,
) -> CredentialField:
    """Shorthand for constructing a CredentialField."""
    return CredentialField(
        db_key=db_key,
        env_var=env_var,
        default=default,
        required=required,
        is_sensitive=is_sensitive,
        help_text=help_text,
        validator=validator,
    )


CredentialSource = Callable[[str], Awaitable[dict[str, object] | None]]
"""Async callback: (config_key) → raw credential dict from external store, or None."""


def parse_bool(value: str) -> bool:
    """Parse a string credential value to bool.

    Recognises ``"true"``, ``"1"``, ``"yes"`` (case-insensitive) as ``True``.
    """
    return value.strip().lower() in ("true", "1", "yes")


_SENTINEL = object()


async def resolve_credentials(
    spec: ChannelCredentialSpec,
    source: CredentialSource | None = None,
) -> dict[str, str]:
    """Resolve credential values from external store or field defaults only.

    For each field the resolution order is:
    1. External store value (via *source* callback) when the field's ``db_key`` is present.
    2. ``field.default``.

    Environment variables are never read — business credentials must come from WebUI/DB
    via the ``source`` callback (server layer) or explicit defaults for optional fields.

    Args:
        spec: The credential schema to resolve.
        source: Async callback returning raw credentials from an external store.
            When None, only ``field.default`` values are used.

    Returns:
        Dict mapping constructor parameter names to resolved string values.
    """
    store_data: dict[str, object] | None = None
    if source is not None:
        store_data = await source(spec.config_key)

    result: dict[str, str] = {}
    for param_name, field in spec.fields:
        value: object = _SENTINEL

        if store_data is not None:
            value = store_data.get(field.db_key, _SENTINEL)

        if value is _SENTINEL:
            value = field.default

        value_str = str(value)

        # Apply validator if provided
        if field.validator:
            try:
                value_str = field.validator(value_str)
            except Exception as e:
                logger.warning(
                    f"Validator failed for field '{param_name}' ({field.db_key}): {e}. Using default value: {field.default!r}"
                )
                value_str = field.default

        result[param_name] = value_str
    return result
