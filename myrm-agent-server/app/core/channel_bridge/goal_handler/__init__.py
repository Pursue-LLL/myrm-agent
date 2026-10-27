"""ChannelGoalCommandHandler package — /goal and /subgoal handling for IM channels.

[INPUT]
- goal_handler.handler (POS: ChannelGoalCommandHandler implementation)

[OUTPUT]
- ChannelGoalCommandHandler: GoalCommandHandler protocol implementation

[POS]
Package entry that keeps ``app.core.channel_bridge.goal_handler.ChannelGoalCommandHandler`` the import path.
"""

from __future__ import annotations

from .handler import ChannelGoalCommandHandler

__all__ = ["ChannelGoalCommandHandler"]
