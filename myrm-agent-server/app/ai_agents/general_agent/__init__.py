"""General Agent模块

基于LangGraph的通用Agent架构，支持完全自主决策。

包含：
- GeneralAgent: 核心通用Agent类
- tools/: 业务工具文件夹
  - answer_user_tool: 用户回答工具
  - web_search_tool: 网络搜索工具
  - web_fetch_tool: 网页抓取工具
- middlewares/: 中间件文件夹
  - smart_prompt_middleware: 智能Prompt中间件
  - tool_selection_middleware: 工具约束中间件（L2 tool_choice 状态机 + 收敛保护）
"""

from .agent import GeneralAgent

__all__ = ["GeneralAgent"]
