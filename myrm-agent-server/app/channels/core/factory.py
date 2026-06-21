"""Channel factory — create channel instances from resolved credentials.

Iterates the provider registry, resolves credentials via each Provider's
``credential_spec`` and ``from_credentials``, and returns ready-to-start
channel instances. The business layer only needs to supply a
``CredentialSource`` callback.

[INPUT]
- channels.core.credentials::resolve_credentials, (POS: Framework-level credential type definitions and generic parser. Providers declare required credentials; business layer provides values via CredentialSource callback.)
- channels.providers.registry::get_channel_class_safe, (POS: Provides GeneratedFile, ArtifactRegistry, RealtimeContentEvent.)

[OUTPUT]
- create_channels: async factory that returns {name: BaseChannel} instances

[POS]
Framework-level channel factory. Decouples credential resolution from
channel instantiation. Invalid provider credentials (`ValueError`) are skipped
with a single warning; unexpected failures retain stack traces.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.core.credentials import (
    CredentialSource,
    resolve_credentials,
)
from app.channels.providers.registry import (
    get_channel_class_safe,
    registered_names,
)

if TYPE_CHECKING:
    from app.channels.core.base import BaseChannel

logger = logging.getLogger(__name__)


async def create_channels(
    source: CredentialSource | None = None,
    *,
    names: frozenset[str] | None = None,
    skip_empty: bool = True,
) -> dict[str, BaseChannel]:
    """Create channel instances for all (or selected) registered providers.

    Args:
        source: Async callback providing raw credentials from an external
            store (DB, vault, file). When ``None``, only env-var and
            default fallbacks are used.
        names: Restrict to these channel names. ``None`` means all
            registered channels.
        skip_empty: When ``True`` (default), skip channels whose resolved
            credentials are all empty strings.

    Returns:
        Dict mapping channel names to instantiated ``BaseChannel`` objects.
    """
    target_names = names if names is not None else registered_names()
    result: dict[str, BaseChannel] = {}

    for name in sorted(target_names):
        cls = get_channel_class_safe(name)
        if cls is None:
            continue

        spec = cls.credential_spec
        if spec is None:
            continue

        creds = await resolve_credentials(spec, source)

        is_empty = True
        for param_name, field in spec.fields:
            val = creds.get(param_name, "")
            if val and val != field.default:
                is_empty = False
                break

        if skip_empty and is_empty:
            logger.debug("Channel '%s': all credentials empty or default, skipping", name)
            continue

        try:
            instance = cls.from_credentials(creds)
            result[name] = instance
            logger.debug("Channel '%s': instance created", name)
        except ValueError as exc:
            logger.warning("Channel '%s': invalid credentials, skipping: %s", name, exc)
        except Exception:
            logger.warning("Channel '%s': failed to create instance", name, exc_info=True)

    return result
