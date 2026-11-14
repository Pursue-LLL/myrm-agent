# survival/

Instance survival monitoring — memory pressure hooks, resource sampling, startup timing.

| File | Role |
| --- | --- |
| `__init__.py` | Package entrypoint |
| `memory_pressure.py` | Global memory pressure coordination; the level comes from the container working set (`memory.current` minus inactive file cache) against the cgroup v2 limit, or from host usage when there is no limit |
| `resource_monitor.py` | High-fidelity resource monitor |
| `startup.py` | Application startup performance toolkit |
