"""Discord channel configuration.

[INPUT]
- (none)

[OUTPUT]
- DiscordChannelConfig: class — Discord Channel Config

[POS]
Discord channel configuration.
"""


class DiscordChannelConfig:
    def __init__(
        self,
        bot_token: str,
        enable_gateway: bool = True,
        allowed_users: list[str] | None = None,
        allowed_guilds: list[str] | None = None,
        *,
        auto_thread: bool = True,
        no_thread_channels: list[str] | None = None,
        voice_enabled: bool = False,
        voice_barge_in_enabled: bool = False,
        voice_wake_words: list[str] | None = None,
        voice_timeout: int = 300,
        voice_auto_join_channel: str | None = None,
        voice_text_channel: str | None = None,
        voice_follow_users: list[str] | None = None,
        voice_allowed_channels: list[str] | None = None,
    ):
        self.bot_token = bot_token
        self.enable_gateway = enable_gateway
        self.allowed_users = allowed_users or []
        self.allowed_guilds = allowed_guilds or []

        self.auto_thread = auto_thread
        self.no_thread_channels: set[str] = set(no_thread_channels or [])

        self.voice_enabled = voice_enabled
        self.voice_barge_in_enabled = voice_barge_in_enabled
        self.voice_wake_words = [w.lower() for w in (voice_wake_words or [])]
        self.voice_timeout = voice_timeout
        self.voice_auto_join_channel = voice_auto_join_channel
        self.voice_text_channel = voice_text_channel
        self.voice_follow_users: list[str] = voice_follow_users or []
        self.voice_allowed_channels: list[tuple[str, str]] = self._parse_allowed_channels(voice_allowed_channels)

    @staticmethod
    def _parse_allowed_channels(
        raw: list[str] | None,
    ) -> list[tuple[str, str]]:
        """Parse 'guild_id:channel_id' strings into (guild_id, channel_id) tuples."""
        result: list[tuple[str, str]] = []
        for entry in raw or []:
            parts = entry.strip().split(":")
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                result.append((parts[0].strip(), parts[1].strip()))
        return result
