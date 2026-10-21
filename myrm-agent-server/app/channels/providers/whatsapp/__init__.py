"""WhatsApp channel provider via Baileys multi-device bridge."""

from ...rendering.converter_registry import FormatConverterRegistry
from .channel import WhatsAppChannel
from .format_converter import md_to_whatsapp

FormatConverterRegistry.register("markdown", "whatsapp", md_to_whatsapp)

__all__ = ["WhatsAppChannel"]
