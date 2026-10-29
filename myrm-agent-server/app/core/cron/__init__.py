"""一次性相对延迟、多频周期日程与生命周期归档的包入口。

[INPUT]
- app.core.cron.relative_delay_parser (POS: 相对时间表达式解析为绝对时间戳)
- app.core.cron.multi_frequency_descriptor (POS: 多频段日程描述符与下一次触发时刻计算)
- app.core.cron.lifecycle_archive_ledger (POS: 任务生命周期状态机与归档账本)
- app.core.cron.universal_visual_scheduler (POS: 把前三者串成注册、到期执行、归档的调度服务)

[OUTPUT]
- RelativeDelayParser, ParsedRelativeDelay, RelativeDelayParseError: 相对延迟解析
- MultiFrequencyDescriptorEngine, ScheduleDescriptor, FrequencyKind, ScheduleCalculationError: 多频日程计算
- LifecycleArchiveLedger, TaskRecord, TaskLifecycleStatus, TaskLedgerError, TaskNotFoundError: 生命周期账本
- UniversalVisualScheduler: 一次性与周期任务的调度服务

[POS]
本包根部这四个模块是相互依赖的一组日程计算与账本类，经此入口统一导出；存储、执行器与投递适配器在 `adapters/`，不经此入口。
"""

from __future__ import annotations

from app.core.cron.lifecycle_archive_ledger import (
    LifecycleArchiveLedger,
    TaskLedgerError,
    TaskLifecycleStatus,
    TaskNotFoundError,
    TaskRecord,
)
from app.core.cron.multi_frequency_descriptor import (
    FrequencyKind,
    MultiFrequencyDescriptorEngine,
    ScheduleCalculationError,
    ScheduleDescriptor,
)
from app.core.cron.relative_delay_parser import (
    ParsedRelativeDelay,
    RelativeDelayParseError,
    RelativeDelayParser,
)
from app.core.cron.universal_visual_scheduler import UniversalVisualScheduler

__all__ = [
    "FrequencyKind",
    "LifecycleArchiveLedger",
    "MultiFrequencyDescriptorEngine",
    "ParsedRelativeDelay",
    "RelativeDelayParseError",
    "RelativeDelayParser",
    "ScheduleCalculationError",
    "ScheduleDescriptor",
    "TaskLedgerError",
    "TaskLifecycleStatus",
    "TaskNotFoundError",
    "TaskRecord",
    "UniversalVisualScheduler",
]
