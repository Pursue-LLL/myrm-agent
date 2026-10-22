"""Agent Avatar Generation and Deterministic SVG Dice Service.

[INPUT]
- seed: str, style: str, background_color: str, prompt: str

[OUTPUT]
- AvatarMetadata, SVG markup string, Image URL

[POS]
app/services/agent/agent_avatar_service.py: Server-side deterministic SVG generation,
AI avatar dispatch, and profile avatar caching.
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum


class AvatarStyle(str, Enum):
    CYBERPUNK = "cyberpunk"
    PIXEL = "pixel"
    BAUHAUS = "bauhaus"
    BEAM = "beam"


@dataclass(frozen=True)
class AvatarMetadata:
    seed: str
    style: AvatarStyle
    background_color: str
    is_locked: bool
    svg_data: str
    image_url: str | None = None
    created_at_epoch: int = field(default_factory=lambda: int(time.time()))


class AgentAvatarService:
    """Service providing deterministic geometric avatar generation and avatar lock state storage."""

    def __init__(self) -> None:
        self._cache: dict[str, AvatarMetadata] = {}

    def generate_deterministic_svg(
        self,
        seed: str,
        style: AvatarStyle = AvatarStyle.BEAM,
        bg_color: str = "#6366f1",
    ) -> str:
        """Generate deterministic SVG avatar markup based on string seed and style preset."""
        # Derive pseudo-random numbers from sha256 hash
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        num1 = int(digest[0:4], 16)
        num2 = int(digest[4:8], 16)
        num3 = int(digest[8:12], 16)
        num4 = int(digest[12:16], 16)

        safe_bg = bg_color if re.match(r"^#[0-9a-fA-F]{6}$", bg_color) else "#4f46e5"

        if style == AvatarStyle.PIXEL:
            # 5x5 symmetric pixel grid
            rects: list[str] = []
            colors = ["#ffffff", "#38bdf8", "#818cf8", "#f472b6", "#fbbf24"]
            accent = colors[num1 % len(colors)]
            for row in range(5):
                for col in range(3):
                    bit = (num2 >> (row * 3 + col)) & 1
                    if bit == 1:
                        fill = accent if (row + col) % 2 == 0 else "#ffffff"
                        rects.append(
                            f'<rect x="{col * 16 + 10}" y="{row * 16 + 10}" width="14" height="14" rx="2" fill="{fill}" />'
                        )
                        if col < 2:
                            sym_col = 4 - col
                            rects.append(
                                f'<rect x="{sym_col * 16 + 10}" y="{row * 16 + 10}" width="14" height="14" rx="2" fill="{fill}" />'
                            )
            inner = "".join(rects)
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">'
                f'<rect width="100" height="100" rx="24" fill="{safe_bg}" />'
                f"{inner}"
                f"</svg>"
            )

        if style == AvatarStyle.CYBERPUNK:
            r1 = (num1 % 25) + 15
            r2 = (num2 % 20) + 10
            x1 = (num3 % 40) + 30
            y1 = (num4 % 40) + 30
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">'
                f"<defs>"
                f'<linearGradient id="cyber-grad" x1="0%" y1="0%" x2="100%" y2="100%">'
                f'<stop offset="0%" stop-color="#06b6d4" />'
                f'<stop offset="100%" stop-color="#d946ef" />'
                f"</linearGradient>"
                f"</defs>"
                f'<rect width="100" height="100" rx="24" fill="{safe_bg}" />'
                f'<circle cx="{x1}" cy="{y1}" r="{r1}" fill="url(#cyber-grad)" opacity="0.85" />'
                f'<polygon points="50,20 {80 - (num1 % 15)},80 {20 + (num2 % 15)},80" fill="#facc15" opacity="0.75" />'
                f'<circle cx="50" cy="50" r="{r2}" fill="#ffffff" opacity="0.9" />'
                f"</svg>"
            )

        if style == AvatarStyle.BAUHAUS:
            c_x = (num1 % 30) + 35
            c_y = (num2 % 30) + 35
            rot = num3 % 360
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">'
                f'<rect width="100" height="100" rx="24" fill="{safe_bg}" />'
                f'<rect x="25" y="25" width="50" height="50" fill="#f43f5e" transform="rotate({rot} 50 50)" opacity="0.8" />'
                f'<circle cx="{c_x}" cy="{c_y}" r="22" fill="#3b82f6" opacity="0.85" />'
                f'<line x1="15" y1="50" x2="85" y2="50" stroke="#fbbf24" stroke-width="6" stroke-linecap="round" />'
                f"</svg>"
            )

        # Default: BEAM warm humanoid glow
        eye_y = 42 + (num1 % 6)
        mouth_y = 66 + (num2 % 6)
        glow_x = (num3 % 30) + 35
        glow_y = (num4 % 30) + 35
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">'
            f"<defs>"
            f'<radialGradient id="beam-glow" cx="50%" cy="50%" r="50%">'
            f'<stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />'
            f'<stop offset="100%" stop-color="{safe_bg}" stop-opacity="0.2" />'
            f"</radialGradient>"
            f"</defs>"
            f'<rect width="100" height="100" rx="24" fill="{safe_bg}" />'
            f'<circle cx="{glow_x}" cy="{glow_y}" r="34" fill="url(#beam-glow)" />'
            f'<circle cx="36" cy="{eye_y}" r="4" fill="#ffffff" />'
            f'<circle cx="64" cy="{eye_y}" r="4" fill="#ffffff" />'
            f'<path d="M 40 {mouth_y} Q 50 {mouth_y + 8} 60 {mouth_y}" stroke="#ffffff" stroke-width="3" fill="none" stroke-linecap="round" />'
            f"</svg>"
        )

    def generate_ai_avatar(self, prompt: str, style: str = "photorealistic") -> str:
        """Simulate or dispatch AI generative image prompt."""
        safe_hash = hashlib.md5(f"{prompt}:{style}".encode("utf-8")).hexdigest()[:10]
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={safe_hash}"

    def set_agent_avatar(self, agent_id: str, metadata: AvatarMetadata) -> AvatarMetadata:
        """Cache avatar metadata for agent."""
        self._cache[agent_id] = metadata
        return metadata

    def get_agent_avatar(self, agent_id: str) -> AvatarMetadata | None:
        """Retrieve cached avatar metadata for agent."""
        return self._cache.get(agent_id)


agent_avatar_service = AgentAvatarService()
