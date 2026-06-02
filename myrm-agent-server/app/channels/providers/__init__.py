"""Channel providers — concrete channel implementations.

Use the registry for lazy-loading::

    from app.channels.providers.registry import (
        get_channel_class,
        load_enabled_channels,
        CHANNEL_META,
    )
"""
