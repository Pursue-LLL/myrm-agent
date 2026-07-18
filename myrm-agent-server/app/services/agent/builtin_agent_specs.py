"""Built-in Agent Specifications (Data Definitions)

[INPUT]
builtin_agent_specs_{core,search,extended,vertical}::_*_BUILTIN_AGENTS (POS: 分段规格数据)

[OUTPUT]
_BUILTIN_AGENTS: Tuple of 25 built-in agent specs (5 core + 2 search + 5 extended + 13 vertical).

[POS]
纯数据层聚合门面：组合各分段规格，供 builtin_initializer 导入。
"""

from app.services.agent.builtin_agent_spec_types import (
    _BuiltInAgentSpec,
    _TOOL_CODING,
    _TOOL_DEFAULT,
    _TOOL_DESIGN,
    _TOOL_MINIMAL,
    _TOOL_RESEARCH,
)
from app.services.agent.builtin_agent_specs_core import _CORE_BUILTIN_AGENTS
from app.services.agent.builtin_agent_specs_extended import _EXTENDED_BUILTIN_AGENTS
from app.services.agent.builtin_agent_specs_search import _SEARCH_BUILTIN_AGENTS
from app.services.agent.builtin_agent_specs_vertical import _VERTICAL_BUILTIN_AGENTS

_BUILTIN_AGENTS: tuple[_BuiltInAgentSpec, ...] = (
    *_CORE_BUILTIN_AGENTS,
    *_SEARCH_BUILTIN_AGENTS,
    *_EXTENDED_BUILTIN_AGENTS,
    *_VERTICAL_BUILTIN_AGENTS,
)

__all__ = [
    "_BUILTIN_AGENTS",
    "_BuiltInAgentSpec",
    "_TOOL_CODING",
    "_TOOL_DEFAULT",
    "_TOOL_DESIGN",
    "_TOOL_MINIMAL",
    "_TOOL_RESEARCH",
]

