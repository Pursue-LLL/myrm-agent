"""业务层工件系统

提供业务层工件处理器，处理框架层发出的 artifacts_ready 事件。

架构原则：
- 框架层发出 artifacts_ready 事件（path + read_content）
- 业务层按需读取、持久化、生成 URL
- 业务层负责关联 user_id/chat_id

⚠️ 命名说明：
- ArtifactProcessor：业务层工件处理器（持久化、生成 URL）
- GeneratedFilesScanner（框架层）：扫描生成的文件路径（不同职责）
"""

from .processor import ArtifactProcessor, LocalArtifactProcessor

__all__ = ["ArtifactProcessor", "LocalArtifactProcessor"]
