# services/kanban/decompose/

TRIAGE 分解域：`decomposer.py` LiteLLM 分解器；`orchestrator.py` 子任务图编排（继承 source_chat_id / model_override）；`prompts.py` 存 EN/ZH 系统提示词与用户模板（从 decomposer.py 拆出以维持 400 行预算）。聚合出口见 `__init__.py`。上级 SSOT：`../_ARCH.md`。
