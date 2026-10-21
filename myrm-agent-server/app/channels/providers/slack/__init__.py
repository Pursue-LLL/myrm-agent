"""Slack channel provider package."""

from ...rendering.converter_registry import FormatConverterRegistry
from .channel import SlackChannel
from .format_converter import md_to_slack_mrkdwn

FormatConverterRegistry.register("markdown", "mrkdwn", md_to_slack_mrkdwn)

__all__ = ["SlackChannel"]
