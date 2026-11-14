"""Camoufox launch with a persisted browser fingerprint.

[INPUT]
- camoufox.async_api::AsyncCamoufox, camoufox.utils::launch_options (POS: Camoufox launch API; imported on use, the package is an optional extra)
- patchright.async_api::Browser (POS: type of the launched browser)
- .browser_launch_env::camoufox_launch_env (POS: environment of launched browser processes)

[OUTPUT]
- launch_camoufox: start Camoufox from the saved fingerprint, generating and saving one when it is missing or unreadable

[POS]
One engine launch, without the retry policy (the launcher owns that). The fingerprint is generated once and saved in
`fingerprint_dir`, so the browser looks the same across restarts; a saved file that is not valid JSON or not a mapping is
deleted and regenerated instead of failing every launch after it.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .browser_launch_env import camoufox_launch_env

if TYPE_CHECKING:
    from patchright.async_api import Browser

logger = logging.getLogger(__name__)

_FINGERPRINT_FILE = "camoufox_fingerprint.json"


def _load_fingerprint(fp_file: Path) -> dict[str, object] | None:
    """The saved fingerprint, or None (the file deleted) when it is not valid JSON or not a mapping."""
    try:
        config = json.loads(fp_file.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("expected dict, got " + type(config).__name__)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Corrupted Camoufox fingerprint at %s — deleting and regenerating",
            fp_file,
        )
        fp_file.unlink(missing_ok=True)
        return None
    logger.debug("Loaded Camoufox fingerprint from %s", fp_file)
    return config


async def launch_camoufox(launch_options: dict[str, object], fingerprint_dir: Path | None) -> Browser:
    """Start Camoufox with its saved fingerprint (generated and saved on first use).

    ``fingerprint_dir`` None keeps nothing: every launch generates a fresh fingerprint.
    """
    from camoufox.async_api import AsyncCamoufox
    from camoufox.utils import launch_options as build_camoufox_options

    fp_file = fingerprint_dir / _FINGERPRINT_FILE if fingerprint_dir else None
    camoufox_config = _load_fingerprint(fp_file) if fp_file and fp_file.is_file() else None

    if camoufox_config is None:
        build_kwargs: dict[str, object] = {
            "headless": launch_options.get("headless", True),
            "fingerprint_preset": True,
            "env": camoufox_launch_env(None),
        }
        proxy = launch_options.get("proxy")
        if proxy is not None:
            build_kwargs["proxy"] = proxy

        loop = asyncio.get_running_loop()
        camoufox_config = await loop.run_in_executor(
            None,
            functools.partial(build_camoufox_options, **build_kwargs),  # type: ignore[arg-type]
        )

        if fp_file:
            fp_file.parent.mkdir(parents=True, exist_ok=True)
            fp_file.write_text(
                json.dumps(camoufox_config, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Camoufox fingerprint saved to %s", fp_file)

    if isinstance(camoufox_config, dict):
        camoufox_config = dict(camoufox_config)
        camoufox_config["env"] = camoufox_launch_env(camoufox_config.get("env"))

    # start() hands back the launched browser although the inherited signature says Playwright.
    return cast("Browser", await AsyncCamoufox(from_options=camoufox_config).start())  # type: ignore[no-untyped-call]
