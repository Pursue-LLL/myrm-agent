"""
@input: 无外部依赖
@output: 对外提供全局系统状态单例
@pos: 系统状态管理 —— 记录数据库降级/恢复等全局状态，供所有层读写

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

from pydantic import BaseModel


class SystemStatus(BaseModel):
    """全局系统状态"""

    database_recovered: bool = False
    database_degraded: bool = False


system_status = SystemStatus()
