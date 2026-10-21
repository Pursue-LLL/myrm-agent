"""e2e_session_runtime 子包：Chrome E2E session 运行时生命周期域。

模块：
- ``lifecycle`` — 相位预算/进度 SSOT（ADMIT/BOOTSTRAP/BODY/TEARDOWN）
- ``registry`` — 统一 session registry（ADMIT through BODY）
- ``snapshot`` — per-pid session snapshot（并行安全进度）
- ``heartbeat`` — 统一 heartbeat SSOT（coordinator + wave lease + runtime）
"""

from __future__ import annotations
