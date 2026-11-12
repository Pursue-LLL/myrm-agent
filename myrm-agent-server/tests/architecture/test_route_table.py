"""Every route mount serves only paths below the route segment it is declared under.

[POS]
tests/architecture/test_route_table.py

[INPUT]
- app.api.router::ROUTER_MOUNTS (POS: every router mounted under the API prefix, with its route segment)
- app.middleware.trailing_slash_alias::iter_route_paths (POS: 去斜杠别名中间件与路由树采集；把路由树展开为完整路径)

[OUTPUT]
- Fails when a mount's router serves a path whose first segment is not the mount's segment: a request for that path
  would not load the group, so the route would answer 404 until something else loaded the group.
- Fails when a segment is not a single path segment.
"""

from __future__ import annotations

import re

from fastapi import APIRouter

from app.api.router import ROUTER_MOUNTS
from app.middleware.trailing_slash_alias import iter_route_paths

_SEGMENT = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def test_segments_are_single_path_segments() -> None:
    malformed = sorted({mount.segment for mount in ROUTER_MOUNTS if not _SEGMENT.fullmatch(mount.segment)})
    assert not malformed, f"route segments must be one lowercase path segment: {malformed}"


def test_every_mount_serves_only_paths_below_its_segment() -> None:
    misplaced: list[str] = []
    for mount in ROUTER_MOUNTS:
        aggregate = APIRouter()
        aggregate.include_router(mount.resolve(), prefix=mount.prefix)
        misplaced.extend(
            f"{mount.module}.{mount.attr} serves {path} but is declared under segment {mount.segment!r}"
            for path in iter_route_paths(aggregate.routes)
            if path.lstrip("/").split("/", 1)[0] != mount.segment
        )
    assert not misplaced, (
        "A request loads the route group named by its first path segment, so every route of a mount must start with the "
        "mount's segment. Fix the segment in app/api/router.py:\n" + "\n".join(misplaced)
    )
