"""Helper functions for Discord channel integration.

[INPUT]
- channels.types.messages::OutboundMessage, (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)
- channels.types.components::ActionButton, (POS: UI component type definitions Cross-channel interactive component abstractions  Support in)

[OUTPUT]
- build_discord_components: 将 Myrm ComponentConvert为 discord.ui.View
- build_discord_embed: 将 Myrm 消息ContentConvert为 discord.Embed
- build_discord_files: 将 Myrm 媒体附件Convert为 discord.File List

[POS]
Pure-function helpers for the Discord channel. Converts framework message objects to Discord native objects.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from app.channels.types.components import (
    ActionButton,
    ButtonStyle,
    SelectMenu,
)
from app.channels.types.messages import OutboundMessage

if TYPE_CHECKING:
    from app.channels.types.messages import MediaAttachment

logger = logging.getLogger(__name__)

# Discord Button Style Mapping
_BUTTON_STYLE_MAP = {
    ButtonStyle.PRIMARY: discord.ButtonStyle.primary,
    ButtonStyle.DANGER: discord.ButtonStyle.danger,
    ButtonStyle.DEFAULT: discord.ButtonStyle.secondary,
}


def build_discord_components(msg: OutboundMessage) -> discord.ui.View | None:
    """Convert OutboundMessage components and quick_replies to a Discord View."""
    if not msg.components and not msg.quick_replies:
        return None

    view = discord.ui.View()
    has_items = False

    # 1. Add standard components (Buttons, SelectMenus)
    for row_idx, row in enumerate(msg.components):
        for item in row:
            if isinstance(item, ActionButton):
                if item.url:
                    # Link button (no custom_id allowed)
                    btn = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=item.label,
                        url=item.url,
                        row=row_idx,
                    )
                else:
                    # Callback button
                    btn = discord.ui.Button(
                        style=_BUTTON_STYLE_MAP.get(item.style, discord.ButtonStyle.secondary),
                        label=item.label,
                        custom_id=f"act:{item.action_id}:{item.value}",
                        row=row_idx,
                    )
                view.add_item(btn)
                has_items = True
            elif isinstance(item, SelectMenu):
                options = [
                    discord.SelectOption(label=opt.label, value=opt.value, description=opt.description)
                    for opt in item.options
                ]
                select = discord.ui.Select(
                    custom_id=f"sel:{item.action_id}",
                    placeholder=item.placeholder,
                    options=options,
                    row=row_idx,
                )
                view.add_item(select)
                has_items = True

    # 2. Add quick replies as secondary buttons (if space permits)
    # Discord allows max 5 rows, 5 buttons per row. We put quick replies in the last available row.
    if msg.quick_replies:
        qr_row = min(4, len(msg.components))  # Try to put in the next row, max row index is 4
        for qr in msg.quick_replies:
            # Only render required quick replies as buttons, or all if we want to be generous
            # For Discord, we render all quick replies as secondary buttons
            btn = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=qr.label,
                custom_id=f"qr:{qr.text}",
                row=qr_row,
            )
            try:
                view.add_item(btn)
                has_items = True
            except ValueError:
                # View is full (max 25 items)
                logger.warning("Discord View is full, dropping remaining quick replies")
                break

    return view if has_items else None


def build_discord_embed(msg: OutboundMessage) -> discord.Embed | None:
    """Build a Discord Embed if the message has reasoning or tool steps."""
    if not msg.reasoning and not msg.tool_steps:
        return None

    embed = discord.Embed(color=discord.Color.blurple())

    if msg.reasoning:
        # Discord embed description limit is 4096
        reasoning_text = msg.reasoning[:4090] + "..." if len(msg.reasoning) > 4096 else msg.reasoning
        embed.add_field(name=" Thinking Process", value=f"```\n{reasoning_text}\n```", inline=False)

    if msg.tool_steps:
        steps_text = "\n".join(
            f"• **{step.label}**" + (f": {step.detail}" if step.detail else "") for step in msg.tool_steps
        )
        steps_text = steps_text[:1020] + "..." if len(steps_text) > 1024 else steps_text
        embed.add_field(name=" Tool Execution", value=steps_text, inline=False)

    return embed


def build_discord_files(media: tuple[MediaAttachment, ...]) -> list[discord.File]:
    """Convert MediaAttachments to discord.File objects."""
    files = []
    for m in media:
        if m.path:
            # Local file upload
            files.append(discord.File(fp=m.path, filename=m.filename))
        elif m.url:
            # For URLs, we usually just append them to the content text in Discord
            # But if we strictly need to upload, we'd need to download it first.
            # Here we assume the channel implementation handles URL downloads before calling this,
            # or we just ignore URLs here and let the content text handle them.
            pass
    return files
