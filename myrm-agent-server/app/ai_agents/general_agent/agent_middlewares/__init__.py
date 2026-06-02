"""GeneralAgent 专用中间件 (Agent Middlewares)

包含 GeneralAgent 专用的 LangGraph Agent 中间件。

中间件列表:
- citation_rules_middleware: 在 final_answer 阶段追加引用规则
- tool_selection_middleware: 工具约束中间件（L2 tool_choice 状态机 + 收敛保护）

注意: 共享中间件（如 user_instructions_middleware）位于 app.ai_agents.agent_middlewares
"""
