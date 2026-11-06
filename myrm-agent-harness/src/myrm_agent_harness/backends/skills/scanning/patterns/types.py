"""[INPUT]
- myrm_agent_harness.backends.skills.scanning.scanner::ScanSeverity (POS: myrm_agent_harness.backends.skills.scanning.scanner)

[OUTPUT]
- （仅导出常量/类型）

[POS]
patterns 子包共用类型；避免每个模式模块重复导入 scanner。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity

PatternList = list[tuple[re.Pattern[str], str, ScanSeverity]]
