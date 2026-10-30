"""Static extraction of symbols and relations from one TypeScript or JavaScript source file.

[INPUT]
- models.py::(CallEdge, CallSite, InheritanceEdge, SymbolKind, SymbolNode) (POS: 代码图谱领域数据模型与契约)
- ast_extractor.py::module_name_for (POS: 静态解析层，把单个源文件解析为符号与关系)
- tree_sitter、tree_sitter_typescript（第三方原生扩展，TypeScript 与 TSX 语法）

[OUTPUT]
- JsTsTreeSitterExtractor: 基于语法树的 TypeScript/JavaScript/TSX 符号、调用、继承抽取，接口与 PythonAstExtractor 一致；
  语法有错的文件按能解析出的部分抽取，不会拒绝

[POS]
静态解析层。与 PythonAstExtractor 同一约定：符号限命名的类、函数、方法，调用记录被调方文本（点分链按书写原样），
调用归属最内层命名的函数或方法，类体与匿名函数里的调用归属外层。不读取文件系统与存储。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Query, QueryCursor

from app.services.code_graph.ast_extractor import module_name_for
from app.services.code_graph.models import (
    CallEdge,
    CallSite,
    ImportEdge,
    InheritanceEdge,
    SymbolKind,
    SymbolNode,
)

# Each pattern captures the definition (or call) node plus the name that names it. A symbol's scope runs from its
# name to the end of its node, so decorators and modifiers in front of the name belong to the enclosing scope.
# Object-literal members and anonymous functions are not symbols; calls inside them belong to the enclosing scope.
# The grammar reads ``await load<T>(x)`` as a call whose callee is ``await load``, so the second call pattern
# restores the callee that was awaited. A call pattern must not name its arguments: the callee comes first, so a
# match waiting for them stays open while a chain such as ``a().b().c()`` is descended, and the open matches make
# the query quadratic in the chain length; ``_record_call`` checks the arguments instead.
_QUERY_SOURCE = """
(function_declaration name: (identifier) @name) @function
(generator_function_declaration name: (identifier) @name) @function
(variable_declarator
  name: (identifier) @name
  value: [(arrow_function) (function_expression) (generator_function)] @function)
(class_declaration name: (type_identifier) @name) @class
(abstract_class_declaration name: (type_identifier) @name) @class
(variable_declarator name: (identifier) @name value: (class) @class)
(class_body
  (method_definition name: [(property_identifier) (private_property_identifier)] @name) @method)
(public_field_definition
  name: [(property_identifier) (private_property_identifier)] @name
  value: [(arrow_function) (function_expression)] @method)
(call_expression function: [(identifier) (member_expression)] @callee) @call
(call_expression function: (await_expression [(identifier) (member_expression)] @callee)) @call
(new_expression constructor: [(identifier) (member_expression)] @callee) @call
"""

_DEFINITION_KINDS = {
    "class": SymbolKind.CLASS,
    "function": SymbolKind.FUNCTION,
    "method": SymbolKind.METHOD,
}


@dataclass(frozen=True)
class _Grammar:
    language: Language
    query: Query


@cache
def _grammar(tsx: bool) -> _Grammar:
    """One compiled grammar per dialect; both are immutable, so extractors share them."""
    language = Language(tree_sitter_typescript.language_tsx() if tsx else tree_sitter_typescript.language_typescript())
    return _Grammar(language, Query(language, _QUERY_SOURCE))


@dataclass(frozen=True)
class _Scope:
    qualified_name: str
    end_byte: int
    is_class: bool


class JsTsTreeSitterExtractor:
    """Symbols, calls and class inheritance of one ``.ts``, ``.tsx``, ``.js`` or ``.jsx`` file."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.module_name = module_name_for(file_path)

        self.symbols: list[SymbolNode] = []
        self.calls: list[CallEdge] = []
        self.inheritances: list[InheritanceEdge] = []
        self.imports: list[ImportEdge] = []

    def extract(self) -> bool:
        """Fill the symbol, call and inheritance lists; a syntax error leaves a partial tree but never fails."""
        grammar = _grammar(tsx=not self.file_path.endswith(".ts"))
        # A parser keeps state while parsing, so every extractor owns one.
        tree = Parser(grammar.language).parse(self.source_code.encode("utf-8"))
        self.symbols.append(
            SymbolNode(
                qualified_name=self.module_name,
                name=self.module_name.split(".")[-1],
                kind=SymbolKind.MODULE,
                file_path=self.file_path,
                line_start=1,
                line_end=len(self.source_code.splitlines()) or 1,
            )
        )
        self._walk(grammar.query, tree.root_node)
        return True

    def _walk(self, query: Query, root: Node) -> None:
        """Replay definitions and calls in source order against a stack of the scopes that are still open.

        Every definition is anchored at its name and every call at the name it calls, which is also where the call
        is reported; the scope of a definition starts at its anchor, so a call is placed by the same rule.
        """
        events: list[tuple[int, bool, dict[str, list[Node]], Node]] = []
        for _, captured in QueryCursor(query).matches(root):
            is_call = "call" in captured
            anchor = _called_name(captured["callee"][0]) if is_call else captured["name"][0]
            events.append((anchor.start_byte, is_call, captured, anchor))
        events.sort(key=lambda event: (event[0], event[1]))
        stack: list[_Scope] = []
        for start_byte, is_call, captured, anchor in events:
            while stack and stack[-1].end_byte <= start_byte:
                stack.pop()
            if is_call:
                caller = next((scope.qualified_name for scope in reversed(stack) if not scope.is_class), self.module_name)
                self._record_call(captured, anchor, caller)
            else:
                stack.append(self._define(captured, anchor, stack[-1].qualified_name if stack else self.module_name))

    def _define(self, captured: dict[str, list[Node]], name_node: Node, parent: str) -> _Scope:
        label = next(label for label in _DEFINITION_KINDS if label in captured)
        node = captured[label][0]
        name = _text(name_node)
        qualified_name = f"{parent}.{name}"
        line = name_node.start_point.row + 1
        self.symbols.append(
            SymbolNode(
                qualified_name=qualified_name,
                name=name,
                kind=_DEFINITION_KINDS[label],
                file_path=self.file_path,
                line_start=line,
                line_end=node.end_point.row + 1,
            )
        )
        if label == "class":
            self._record_inheritance(node, qualified_name, line)
        return _Scope(qualified_name, node.end_byte, label == "class")

    def _record_inheritance(self, node: Node, qualified_name: str, line: int) -> None:
        for heritage in (child for child in node.children if child.type == "class_heritage"):
            for clause in (child for child in heritage.children if child.type == "extends_clause"):
                value = clause.child_by_field_name("value")
                super_type = _dotted_name(value) if value is not None else ""
                if super_type:
                    self.inheritances.append(
                        InheritanceEdge(sub_type=qualified_name, super_type=super_type, file_path=self.file_path, line=line)
                    )

    def _record_call(self, captured: dict[str, list[Node]], name_node: Node, caller: str) -> None:
        node = captured["call"][0]
        arguments = node.child_by_field_name("arguments")
        # A tagged template is not a call; ``new Foo`` without parentheses is one.
        if node.type == "call_expression" and (arguments is None or arguments.type != "arguments"):
            return
        self.calls.append(
            CallEdge(
                caller=caller,
                callee=_dotted_name(captured["callee"][0]),
                call_site=CallSite(
                    file_path=self.file_path,
                    line=name_node.start_point.row + 1,
                    col=name_node.start_point.column,
                    end_line=node.end_point.row + 1,
                    end_col=node.end_point.column,
                    arg_count=sum(child.type != "comment" for child in arguments.named_children) if arguments else 0,
                ),
            )
        )


def _called_name(callee: Node) -> Node:
    """The node that carries the name a call is written with: the method of a member call, else the callee itself."""
    member = callee.child_by_field_name("property") if callee.type == "member_expression" else None
    return member if member is not None else callee


def _text(node: Node) -> str:
    return (node.text or b"").decode("utf-8")


def _dotted_name(node: Node) -> str:
    """Name of an identifier or member chain as written (``this.store.save``); what stands left of a base that is
    not a plain name (a call result, an index) is dropped, so ``load().items.save`` is ``items.save``.

    Walks the chain in a loop: generated code can chain members deeper than the recursion limit.
    """
    parts: list[str] = []
    while True:
        if node.type in ("identifier", "this"):
            parts.append(_text(node))
            break
        if node.type == "non_null_expression" and node.named_children:
            node = node.named_children[0]
            continue
        base = node.child_by_field_name("object") if node.type == "member_expression" else None
        member = node.child_by_field_name("property") if base is not None else None
        if base is None or member is None:
            break
        parts.append(_text(member))
        node = base
    return ".".join(reversed(parts))
