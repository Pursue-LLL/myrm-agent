"""业务层工件系统

提供业务层工件处理器，处理框架层发出的 artifacts_ready 事件。

架构原则：
- 框架层发出 artifacts_ready 事件（path + read_content）
- 业务层按需读取、持久化、生成 URL
- 业务层负责关联 user_id/chat_id

生产环境统一使用 LocalArtifactProcessor（见 platform_utils.get_artifact_processor）。
"""

from . import listener
from .processor import LocalArtifactProcessor

__all__ = ["LocalArtifactProcessor", "listener"]
