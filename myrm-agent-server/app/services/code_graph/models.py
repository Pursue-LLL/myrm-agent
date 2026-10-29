"""
@input: 接收源代码文件路径与 AST 节点请求
@output: 提供基础数据结构定义（SymbolNode, CallEdge, CallSite, ParsedFile, IndexStats）
@pos: 代码图谱领域数据模型与契约
"""

from dataclasses import asdict, dataclass, field
from enum import Enum


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

    def to_dict(self) -> dict[str, object]:
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

    def to_dict(self) -> dict[str, object]:
        res: dict[str, object] = asdict(self)
        res["kind"] = self.kind.value
        return res


@dataclass
class CallEdge:
    caller: str
    callee: str
    call_site: CallSite

    def to_dict(self) -> dict[str, object]:
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

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ImportEdge:
    importer_module: str
    imported_symbol: str
    file_path: str
    line: int
    col: int
    alias: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ParsedFile:
    """One source file's extraction result, with the fingerprint that decides whether it must be parsed again."""

    file_path: str
    mtime_ns: int
    size: int
    symbols: list[SymbolNode]
    calls: list[CallEdge]
    inheritances: list[InheritanceEdge]
    imports: list[ImportEdge]


@dataclass
class IndexStats:
    """State of the index after a run: the totals are index-wide, the other counters describe this run."""

    total_files: int
    total_symbols: int
    total_calls: int
    elapsed_ms: float
    updated_files: int = 0
    removed_files: int = 0
    skipped_files: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
