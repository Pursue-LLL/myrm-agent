"""
@input: 接收源代码文件路径与 AST 节点请求
@output: 提供基础数据结构定义（SymbolNode, CallEdge, CallSite, IndexStats）
@pos: 代码图谱领域数据模型与契约
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SymbolKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"


@dataclass(frozen=True)
class CallSite:
    file_path: str
    line: int
    col: int
    end_line: int
    end_col: int
    arg_count: int = 0
    kwarg_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SymbolNode:
    qualified_name: str
    name: str
    kind: SymbolKind
    file_path: str
    line_start: int
    line_end: int
    docstring: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        res["kind"] = self.kind.value
        return res


@dataclass
class CallEdge:
    caller: str
    callee: str
    call_site: CallSite

    def to_dict(self) -> dict[str, Any]:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "call_site": self.call_site.to_dict(),
        }


@dataclass
class InheritanceEdge:
    sub_type: str
    super_type: str
    file_path: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImportEdge:
    importer_module: str
    imported_symbol: str
    file_path: str
    line: int
    col: int
    alias: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IndexStats:
    total_files: int
    total_symbols: int
    total_calls: int
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
