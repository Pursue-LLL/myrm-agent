"""Route groups load in any order: the last group first leaves the same aggregate as the declared order.

[INPUT]
- app.api.router::ROUTER_MOUNTS / EAGER_SEGMENTS / route_loader (POS: 路由挂载表与按路由段按需加载的聚合路由)
- app.server.lazy_routes::LazyRouteLoader (POS: 路由组按需加载，终态与按声明顺序急切聚合同构)
- app.middleware.trailing_slash_alias::iter_route_paths (POS: 去斜杠别名中间件与路由树采集；把路由树展开为完整路径)

[OUTPUT]
- Regression coverage that no route group needs another one imported first and that the aggregate's route order does
  not depend on the order the groups were loaded in

[POS]
Startup tests. A request loads the group its path names, so the first group to load is whichever one the user touches
first. A module cycle that only resolves from one side imports fine in the declared order and fails the first request
in another; the groups are loaded last-to-first in a fresh interpreter, so no module imported by pytest hides one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_RESULT_FILE_ENV = "MYRM_ROUTE_ORDER_RESULT_FILE"

_PROBE_SOURCE = f"""
import json
import os
from pathlib import Path

import app.main  # noqa: F401
from app.api.router import EAGER_SEGMENTS, ROUTER_MOUNTS, route_loader
from app.config.deploy_mode import is_local_mode
from app.middleware.trailing_slash_alias import iter_route_paths
from app.server.lazy_routes import LazyRouteLoader

for segment in reversed(route_loader.pending_segments()):
    route_loader.ensure_loaded(segment)

declared = LazyRouteLoader(ROUTER_MOUNTS, local_mode=is_local_mode(), eager_segments=EAGER_SEGMENTS)
declared.load_all()

reversed_paths = list(iter_route_paths(route_loader.router.routes))
result = dict(
    pending=list(route_loader.pending_segments()),
    route_count=len(reversed_paths),
    same_route_order=reversed_paths == list(iter_route_paths(declared.router.routes)),
)
Path(os.environ[{_RESULT_FILE_ENV!r}]).write_text(json.dumps(result))
"""


@pytest.fixture(scope="module")
def reverse_order_probe(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    result_file = tmp_path_factory.mktemp("route-group-order") / "result.json"
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE_SOURCE],
        cwd=_SERVER_ROOT,
        env={**os.environ, _RESULT_FILE_ENV: str(result_file)},
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    payload: dict[str, object] = json.loads(result_file.read_text())
    return payload


def test_every_group_loads_when_the_last_one_loads_first(reverse_order_probe: dict[str, object]) -> None:
    assert reverse_order_probe["pending"] == []
    assert reverse_order_probe["route_count"]


def test_the_aggregate_keeps_the_declared_route_order_whatever_the_load_order(reverse_order_probe: dict[str, object]) -> None:
    assert reverse_order_probe["same_route_order"] is True
