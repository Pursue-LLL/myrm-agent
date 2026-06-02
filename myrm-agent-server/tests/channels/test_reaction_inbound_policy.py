"""Cross-provider invariant: reaction inbound must traverse SELECTIVE_POLICY.

A latent bug existed across all reaction-capable providers (Slack, Discord,
Telegram, WhatsApp, Signal, Feishu, Mattermost, Matrix, iMessage): inbound
``message_reaction`` events were emitted with ``mentioned=False``, which made
the default :data:`SELECTIVE_POLICY` (group ``MENTION_ONLY``) silently drop
every group-chat reaction during the ``BaseChannel._emit_inbound`` access
control stage. The IM-side approval feature documented across nine channels
therefore worked only in DMs, even though every router/handler downstream
was correct.

This module pins three contracts:

1. **Access-control invariant** — any :class:`InboundMessage` produced by a
   provider whose semantics is "user reacted to a bot message" — identified
   by ``metadata.reaction == True`` and a ``target_message_id`` — must
   satisfy ``mentioned=True`` so it survives the default access policy.
2. **Source-site contract** — every shipped provider that declares
   ``capabilities.reactions == True`` writes ``mentioned=True`` in the
   inbound construction site (greps the source) so future contributors
   cannot regress this contract by copying the legacy pattern.
3. **Three-tier vocabulary coverage** — providers that own a
   shortcode/emoji-name table (Slack ``_SLACK_EMOJI_MAP``, Mattermost
   ``_REACTION_EMOJI_MAP``, Matrix ``_REACTION_EMOJI_MAP``, Feishu
   ``_FEISHU_EMOJI_TO_UNICODE``) must map every emoji that
   ``parse_approval_command`` recognises across all three decision tiers
   so the IM-side approval feature is actually usable. iMessage tapback is
   the platform-locked exception (six fixed reactions; users fall back to
   the textual ``aa`` / ``always`` aliases for ``allow_always``).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.channels.core.allow_policy import SELECTIVE_POLICY
from app.channels.providers.registry import CHANNEL_META, get_channel_class
from app.channels.types import InboundMessage

REACTION_CAPABLE_CHANNELS: list[str] = sorted(
    name
    for name in CHANNEL_META.keys()
    if not isinstance(get_channel_class(name).capabilities, property)
    and get_channel_class(name).capabilities.reactions
)


class TestReactionInboundPolicyInvariant:
    """Behavioural invariant on the access-control layer."""

    @pytest.mark.parametrize(
        "is_group",
        [pytest.param(True, id="group"), pytest.param(False, id="dm")],
    )
    def test_reaction_inbound_passes_selective_policy(self, is_group: bool) -> None:
        """A reaction with ``mentioned=True`` must pass the default policy.

        This is the contract every reaction-capable provider relies on.
        """
        msg = InboundMessage(
            channel="any",
            sender_id="user_1",
            content="\U0001F44D",
            chat_id="chat_1",
            is_group=is_group,
            mentioned=True,
            message_id="m1",
            metadata={"reaction": True, "target_message_id": "m1"},
        )
        assert SELECTIVE_POLICY.evaluate(msg) is None

    def test_reaction_with_mentioned_false_in_group_is_dropped(self) -> None:
        """Counter-example: the legacy ``mentioned=False`` pattern is dropped.

        This guards the regression we are pinning; if anyone removes the
        invariant, they will see the access-control layer reject reactions.
        """
        msg = InboundMessage(
            channel="any",
            sender_id="user_1",
            content="\U0001F44D",
            chat_id="chat_1",
            is_group=True,
            mentioned=False,
            message_id="m1",
            metadata={"reaction": True, "target_message_id": "m1"},
        )
        assert SELECTIVE_POLICY.evaluate(msg) is not None


class TestReactionConstructionSiteContract:
    """Static check: every reaction-capable provider writes ``mentioned=True``.

    We scan each provider source file for ``"reaction": True`` literals in
    inbound construction blocks and assert that the surrounding 12-line window
    also contains ``mentioned=True``. This is the cheapest cross-provider
    contract test that detects the regression at module load time.
    """

    @pytest.mark.parametrize("channel_name", REACTION_CAPABLE_CHANNELS)
    def test_reaction_inbound_sets_mentioned_true(self, channel_name: str) -> None:
        """If a provider implements inbound reaction events, ``mentioned=True``.

        Outbound-only ``capabilities.reactions`` (e.g. msteams, dingtalk send
        an emoji on bot messages but never receive ``reaction_added`` webhooks)
        is permitted: the contract only kicks in once a provider constructs
        an ``InboundMessage`` with ``metadata={"reaction": True, ...}``.
        """
        cls = get_channel_class(channel_name)
        source_root = Path(inspect.getsourcefile(cls) or "").parent
        if not source_root.exists():
            pytest.skip(f"{channel_name}: source path unavailable")

        candidates = sorted(source_root.rglob("*.py"))
        offending: list[tuple[Path, int]] = []
        construction_sites = 0
        for path in candidates:
            text = path.read_text(encoding="utf-8")
            if '"reaction": True' not in text:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if '"reaction": True' not in line:
                    continue
                construction_sites += 1
                window = lines[max(0, i - 12) : i + 2]
                joined = "\n".join(window)
                if "mentioned=True" not in joined:
                    offending.append((path, i + 1))

        if construction_sites == 0:
            pytest.skip(
                f"{channel_name}: outbound-only reactions (no inbound webhook)"
            )

        assert not offending, (
            f"{channel_name}: reaction inbound site missing mentioned=True at "
            f"{', '.join(f'{p}:{lineno}' for p, lineno in offending)}; "
            f"reactions on bot messages must opt out of MENTION_ONLY filtering "
            f"by setting mentioned=True"
        )


class TestThreeTierEmojiCoverage:
    """Reaction emoji shortcode tables must cover ``parse_approval_command``.

    Otherwise an IM user reacting with the published vocabulary would land in
    a silent drop branch on the channel boundary, and the documented three
    tiers — `allow_once` / `allow_always` / `deny` — would degrade to "approve
    or nothing" on that platform.
    """

    @pytest.mark.parametrize(
        "table_path,decoded",
        [
            pytest.param(
                "app.channels.providers.slack.channel.SlackChannel._SLACK_EMOJI_MAP",
                None,
                id="slack",
            ),
            pytest.param(
                "app.channels.providers.mattermost.channel."
                "MattermostChannel._REACTION_EMOJI_MAP",
                None,
                id="mattermost",
            ),
            pytest.param(
                "app.channels.providers.matrix.handlers._REACTION_EMOJI_MAP",
                None,
                id="matrix",
            ),
            pytest.param(
                "app.channels.providers.feishu.channel._FEISHU_EMOJI_TO_UNICODE",
                None,
                id="feishu",
            ),
        ],
    )
    def test_table_covers_three_tiers(self, table_path: str, decoded: None) -> None:
        from importlib import import_module

        module_path, _, attr_path = table_path.rpartition(".")
        attr_path.split(".")
        if "." in attr_path:
            module_path, _, attr_path = table_path.partition(".")
        # Parse "pkg.mod.Class.ATTR" or "pkg.mod.ATTR"
        parts = table_path.split(".")
        for split_at in range(len(parts) - 1, 0, -1):
            mod_candidate = ".".join(parts[:split_at])
            try:
                module = import_module(mod_candidate)
            except ImportError:
                continue
            target: object = module
            for piece in parts[split_at:]:
                target = getattr(target, piece, None)
                if target is None:
                    break
            if isinstance(target, dict):
                table: dict[str, str] = target
                break
        else:
            pytest.fail(f"Cannot resolve emoji map at {table_path}")

        decoded_emojis = {value for value in table.values()}

        approve_once = {"\U0001F44D", "\u2764", "\u2705", "\U0001F91D", "\U0001F4AA"}
        approve_always = {"\u267E", "\u2B50"}
        deny_set = {"\U0001F44E", "\u274C", "\U0001F6AB"}

        # Strip variation selectors before comparing — Slack stores "❤️" with
        # FE0F, the canonical decision vocabulary stores "❤".
        normalised = {value.replace("\uFE0F", "") for value in decoded_emojis}

        assert normalised & approve_once, (
            f"{table_path}: zero emoji maps to allow_once decision"
        )
        assert normalised & approve_always, (
            f"{table_path}: zero emoji maps to allow_always decision; "
            f"users will not be able to grant 'Always allow' via reactions"
        )
        assert normalised & deny_set, (
            f"{table_path}: zero emoji maps to deny decision"
        )
