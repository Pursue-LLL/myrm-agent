"""A maintenance load sensor whose level the test sets.

[INPUT]
- myrm_agent_harness.runtime.maintenance.protocols::LoadSensor, SystemLoadLevel, SystemLoadSnapshot (POS: the sensor contract the scheduler reads)

[OUTPUT]
- FakeLoadSensor: reports the level it was given, or the one `set_level` last set

[POS]
Pytest-only helper shared by the maintenance scheduler and quota-integration tests, so each test states the load it
runs under and not how a sensor reads it.
"""

from __future__ import annotations

from myrm_agent_harness.runtime.maintenance.protocols import LoadSensor, SystemLoadLevel, SystemLoadSnapshot


class FakeLoadSensor(LoadSensor):
    """Reports a fixed load level that a test can change."""

    def __init__(self, level: SystemLoadLevel = SystemLoadLevel.IDLE) -> None:
        self._level = level

    def set_level(self, level: SystemLoadLevel) -> None:
        self._level = level

    def read(self) -> SystemLoadSnapshot:
        return SystemLoadSnapshot(level=self._level, cpu_percent=0, memory_percent=0)
