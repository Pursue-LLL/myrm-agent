"""Browser task spaces service package for server layer."""

from .task_space_service import TaskSpaceInfo, TaskSpaceService, get_task_space_service

__all__ = [
    "TaskSpaceInfo",
    "TaskSpaceService",
    "get_task_space_service",
]
