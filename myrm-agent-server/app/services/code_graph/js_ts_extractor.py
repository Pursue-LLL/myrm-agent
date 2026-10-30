"""Static extraction of symbols and relations from one TypeScript or JavaScript source file.

[INPUT]
- models.py::(CallEdge, CallSite, ImportEdge, InheritanceEdge, SymbolKind, SymbolNode, module_name_for) (POS: 代码图谱领域数据模型与契约)
- tree_sitter、tree_sitter_typescript（第三方原生扩展，TypeScript 与 TSX 语法）

[OUTPUT]
- JsTsTreeSitterExtractor: 基于语法树的 TypeScript/JavaScript/TSX 符号、调用、继承抽取，接口与 PythonAstExtractor 一致；
  语法有错的文件按能解析出的部分抽取，不会拒绝

[POS]
静态解析层。与 PythonAstExtractor 同一约定：符号限命名的类、函数、方法，调用记录被调方文本（点分链按书写原样），
调用归属最内层命名的函数或方法，类体与匿名函数里的调用归属外层。不读取文件系统与存储。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

import tree_sitter_typescript
from tree_sitter import Language, Node, Parser, Tree

from app.services.code_graph.models import (
    CallEdge,
    CallSite,
    ImportEdge,
    InheritanceEdge,
    SymbolKind,
    SymbolNode,
    module_name_for,
)

# A qualified name repeats the name of every enclosing definition, so a file that nests named functions n levels deep
# holds n^2 characters of names (a 1 MB file nested 76,000 deep took 5 GB). Real code nests a handful of levels;
# a definition inside more than this many open definitions is not a symbol, and its calls belong to the deepest one.
MAX_SCOPE_DEPTH = 32

_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "generator_function"})
_FIELD_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression"})
_MEMBER_NAMES = frozenset({"property_identifier", "private_property_identifier"})
_CALLEES = frozenset({"identifier", "member_expression"})


@cache
def _language(tsx: bool) -> Language:
    """One compiled grammar per dialect; it is immutable, so extractors share it."""
    return Language(tree_sitter_typescript.language_tsx() if tsx else tree_sitter_typescript.language_typescript())


@dataclass(frozen=True)
class _Scope:
    """A named definition that is still open: it runs from its name to the end of its node."""

    qualified_name: str
    start_byte: int
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

        self._scopes: list[_Scope] = []
        self._parent_types: list[str] = []
        self._visitors: dict[str, Callable[[Node], None]] = {
            "function_declaration": self._visit_function,
            "generator_function_declaration": self._visit_function,
            "class_declaration": self._visit_class,
            "abstract_class_declaration": self._visit_class,
            "variable_declarator": self._visit_declarator,
            "method_definition": self._visit_method,
            "public_field_definition": self._visit_field,
            "call_expression": self._visit_call,
            "new_expression": self._visit_call,
        }

    def extract(self) -> bool:
        """Fill the symbol, call and inheritance lists; a syntax error leaves a partial tree but never fails."""
        # A parser keeps state while parsing, so every extractor owns one.
        tree = Parser(_language(tsx=not self.file_path.endswith(".ts"))).parse(self.source_code.encode("utf-8"))
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
        self._walk(tree)
        return True

    def _walk(self, tree: Tree) -> None:
        """Visit every node once in source order, keeping the stack of definitions that are still open.

        A cursor walk costs the same for every node however deep it sits, and it is a loop because generated code
        nests deeper than the recursion limit. A query would be shorter, but its cost per node grows with the depth
        of the tree (tens of thousands of nested parentheses take minutes, with the GIL held) and it silently drops
        matches once more than 32,767 are open at the same time.
        """
        scopes, parent_types = self._scopes, self._parent_types
        cursor = tree.walk()
        while True:
            node = cursor.node
            if node is None:
                return
            while scopes and scopes[-1].end_byte <= node.start_byte:
                scopes.pop()
            visit = self._visitors.get(node.type)
            if visit is not None:
                visit(node)
            if cursor.goto_first_child():
                parent_types.append(node.type)
                continue
            while not cursor.goto_next_sibling():
                if not cursor.goto_parent():
                    return
                parent_types.pop()

    def _visit_function(self, node: Node) -> None:
        name = node.child_by_field_name("name")
        if name is not None and name.type == "identifier":
            self._define(node, name, SymbolKind.FUNCTION)

    def _visit_class(self, node: Node) -> None:
        name = node.child_by_field_name("name")
        if name is not None and name.type == "type_identifier":
            self._define(node, name, SymbolKind.CLASS)

    def _visit_declarator(self, node: Node) -> None:
        """``const f = () => {}`` defines a function and ``const C = class {}`` a class; other values define nothing."""
        name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
        if name is None or value is None or name.type != "identifier":
            return
        if value.type in _FUNCTION_VALUES:
            self._define(value, name, SymbolKind.FUNCTION)
        elif value.type == "class":
            self._define(value, name, SymbolKind.CLASS)

    def _visit_method(self, node: Node) -> None:
        """Only class methods are symbols; the methods of an object literal belong to the enclosing scope."""
        name = node.child_by_field_name("name")
        if self._parent_types and self._parent_types[-1] == "class_body" and name is not None and name.type in _MEMBER_NAMES:
            self._define(node, name, SymbolKind.METHOD)

    def _visit_field(self, node: Node) -> None:
        """A class field holding an arrow or function expression is a method."""
        name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
        if name is not None and value is not None and name.type in _MEMBER_NAMES and value.type in _FIELD_FUNCTION_VALUES:
            self._define(node, name, SymbolKind.METHOD)

    def _visit_call(self, node: Node) -> None:
        callee = _callee(node)
        if callee is None:
            return
        arguments = node.child_by_field_name("arguments")
        # A tagged template is not a call; ``new Foo`` without parentheses is one.
        if node.type == "call_expression" and (arguments is None or arguments.type != "arguments"):
            return
        # The call is reported, and attributed to a scope, at the name it calls.
        name = _called_name(callee)
        self.calls.append(
            CallEdge(
                caller=self._enclosing(name.start_byte, skip_classes=True) or self.module_name,
                callee=_dotted_name(callee),
                call_site=CallSite(
                    file_path=self.file_path,
                    line=name.start_point.row + 1,
                    col=name.start_point.column,
                    end_line=node.end_point.row + 1,
                    end_col=node.end_point.column,
                    arg_count=sum(child.type != "comment" for child in arguments.named_children) if arguments else 0,
                ),
            )
        )

    def _enclosing(self, position: int, *, skip_classes: bool) -> str | None:
        """Innermost open definition that has begun at ``position``; one whose name is still ahead (a decorator or
        heritage clause in front of the name) does not enclose it. Classes are skipped for calls: the calls in a
        class body belong to the code that declares the class."""
        for scope in reversed(self._scopes):
            if scope.start_byte <= position and not (skip_classes and scope.is_class):
                return scope.qualified_name
        return None

    def _define(self, node: Node, name_node: Node, kind: SymbolKind) -> None:
        if len(self._scopes) >= MAX_SCOPE_DEPTH:
            return
        name = _text(name_node)
        qualified_name = f"{self._enclosing(name_node.start_byte, skip_classes=False) or self.module_name}.{name}"
        line = name_node.start_point.row + 1
        self.symbols.append(
            SymbolNode(
                qualified_name=qualified_name,
                name=name,
                kind=kind,
                file_path=self.file_path,
                line_start=line,
                line_end=node.end_point.row + 1,
            )
        )
        if kind is SymbolKind.CLASS:
            self._record_inheritance(node, qualified_name, line)
        self._scopes.append(_Scope(qualified_name, name_node.start_byte, node.end_byte, kind is SymbolKind.CLASS))

    def _record_inheritance(self, node: Node, qualified_name: str, line: int) -> None:
        for heritage in (child for child in node.children if child.type == "class_heritage"):
            for clause in (child for child in heritage.children if child.type == "extends_clause"):
                value = clause.child_by_field_name("value")
                super_type = _dotted_name(value) if value is not None else ""
                if super_type:
                    self.inheritances.append(
                        InheritanceEdge(sub_type=qualified_name, super_type=super_type, file_path=self.file_path, line=line)
                    )


def _callee(call: Node) -> Node | None:
    """The plain or member name a call or ``new`` expression calls; calling anything else records no edge.

    The grammar reads ``await load<T>(x)`` as a call whose callee is ``await load``, so an awaited callee is unwrapped.
    """
    callee = call.child_by_field_name("constructor" if call.type == "new_expression" else "function")
    if callee is not None and callee.type == "await_expression":
        callee = next((child for child in callee.children if child.type in _CALLEES), None)
    return callee if callee is not None and callee.type in _CALLEES else None


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
