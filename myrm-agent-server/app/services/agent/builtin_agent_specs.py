"""Built-in Agent Specifications (Data Definitions)

[INPUT]
app.services.agent.builtin_specs.{core,search,extended,vertical}::_*_BUILTIN_AGENTS (POS: 分段规格数据)

[OUTPUT]
_BUILTIN_AGENTS: Tuple of 26 built-in agent specs (5 core + 2 search + 5 extended + 14 vertical).

[POS]
纯数据层聚合门面：组合各分段规格，供 builtin_initializer 导入。
"""

from app.services.agent.builtin_specs.core import _CORE_BUILTIN_AGENTS
from app.services.agent.builtin_specs.extended import _EXTENDED_BUILTIN_AGENTS
from app.services.agent.builtin_specs.search import _SEARCH_BUILTIN_AGENTS
from app.services.agent.builtin_specs.types import (
    _BuiltInAgentSpec,
    _TOOL_CODING,
    _TOOL_DEFAULT,
    _TOOL_DESIGN,
    _TOOL_MINIMAL,
    _TOOL_RESEARCH,
    _TOOL_VIDEO_STUDIO,
)
from app.services.agent.builtin_specs.vertical import _VERTICAL_BUILTIN_AGENTS

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
    "_TOOL_VIDEO_STUDIO",
]

