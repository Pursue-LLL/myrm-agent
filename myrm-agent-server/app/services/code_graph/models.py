"""Domain data model of the code graph.

[INPUT]
- 无内部依赖（仅标准库 dataclasses、enum）

[OUTPUT]
- SymbolKind: 符号种类枚举
- SymbolNode、CallEdge、InheritanceEdge、ImportEdge: 符号以及调用、继承、导入关系的记录
- CallSite: 一次调用在源码中的位置、参数个数与关键字参数名
- ParsedFile: 单个文件的解析结果及其指纹（决定是否需要重新解析）
- IndexStats: 一次索引同步后的统计

[POS]
代码图谱领域数据模型与契约。定义符号、调用、继承、导入关系，单文件解析结果与同步统计，供抽取器、存储与服务共用。
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
    """State of the index after a run: the totals are index-wide, the other counters describe this run.

    ``truncated`` is True when the workspace file listing reached its cap, so the files beyond it are not indexed.
    """

    total_files: int
    total_symbols: int
    total_calls: int
    elapsed_ms: float
    updated_files: int = 0
    removed_files: int = 0
    skipped_files: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
