"""Static extraction of symbols and relations from one Python source file.

[INPUT]
- models.py::(CallEdge, CallSite, ImportEdge, InheritanceEdge, SymbolKind, SymbolNode) (POS: 代码图谱领域数据模型与契约)
- ast、pathlib（标准库）

[OUTPUT]
- module_name_for: 相对路径到点分模块名的规则，Python 与 JS/TS 两个抽取器共用
- PythonAstExtractor: 基于原生 ast 的 Python 符号、调用、继承、导入抽取；不是合法 Python 时返回 False

[POS]
静态解析层。把单个源文件的路径与源码文本解析为符号和关系，不读取文件系统与存储。
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from app.services.code_graph.models import (
    CallEdge,
    CallSite,
    ImportEdge,
    InheritanceEdge,
    SymbolKind,
    SymbolNode,
)


def module_name_for(file_path: str) -> str:
    """Dotted module name from a path relative to the index root.

    The Python and the JS/TS extractor use this rule so that two files with the same basename in different
    directories keep different qualified names.
    """
    path = Path(file_path)
    parts = [part for part in path.with_suffix("").parts if part not in (".", "/")]
    return ".".join(parts) if parts else path.stem


@dataclass(frozen=True)
class _Context:
    """Where the code being walked sits: ``scope`` prefixes names defined here, ``caller`` owns calls found here,
    ``in_class`` marks functions defined here as methods."""

    scope: str
    caller: str
    in_class: bool


class PythonAstExtractor:
    """基于 Python 3.13 原生 ast 模块的高性能静态分析抽取器。"""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.module_name = module_name_for(file_path)

        self.symbols: list[SymbolNode] = []
        self.calls: list[CallEdge] = []
        self.inheritances: list[InheritanceEdge] = []
        self.imports: list[ImportEdge] = []

    def extract(self) -> bool:
        """Fill the symbol, call, inheritance and import lists; False when the source is not valid Python."""
        try:
            tree = ast.parse(self.source_code, filename=self.file_path)
        except SyntaxError:
            return False

        self.symbols.append(
            SymbolNode(
                qualified_name=self.module_name,
                name=self.module_name.split(".")[-1],
                kind=SymbolKind.MODULE,
                file_path=self.file_path,
                line_start=1,
                line_end=len(self.lines) if self.lines else 1,
                docstring=ast.get_docstring(tree) or "",
            )
        )
        self._walk(tree)
        return True

    def _walk(self, tree: ast.Module) -> None:
        """Visit every node once, in source order, with the context its definitions and calls belong to.

        Definitions and imports are found at any depth (inside ``if``, ``try``, ``with`` ...). Decorators,
        default values, base classes and class keywords run when the definition is executed, so they are
        visited in the enclosing context, not in the new one. The walk is iterative: generated code can nest
        deeper than the recursion limit.
        """
        stack: list[tuple[ast.AST, _Context]] = [(tree, _Context(self.module_name, self.module_name, False))]
        while stack:
            node, ctx = stack.pop()
            pending: list[tuple[ast.AST, _Context]]
            if isinstance(node, ast.ClassDef):
                inner = self._define_class(node, ctx)
                pending = [(part, ctx) for part in (*node.decorator_list, *node.bases, *node.keywords)]
                pending += [(statement, inner) for statement in node.body]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = self._define_function(node, ctx)
                header: list[ast.AST] = [*node.decorator_list, node.args]
                if node.returns is not None:
                    header.append(node.returns)
                pending = [(part, ctx) for part in header]
                pending += [(statement, inner) for statement in node.body]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self._record_import(node, alias.name, alias)
                continue
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    self._record_import(node, f"{module}.{alias.name}" if module else alias.name, alias)
                continue
            else:
                if isinstance(node, ast.Call):
                    self._record_call(node, ctx.caller)
                pending = [(child, ctx) for child in ast.iter_child_nodes(node)]
            stack.extend(reversed(pending))

    def _define_class(self, node: ast.ClassDef, ctx: _Context) -> _Context:
        qname = f"{ctx.scope}.{node.name}"
        self.symbols.append(
            SymbolNode(
                qualified_name=qname,
                name=node.name,
                kind=SymbolKind.CLASS,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node) or "",
            )
        )
        for base in node.bases:
            base_name = self._resolve_name(base)
            if base_name:
                self.inheritances.append(
                    InheritanceEdge(sub_type=qname, super_type=base_name, file_path=self.file_path, line=node.lineno)
                )
        # Calls in the class body run when the class is defined, so they belong to the enclosing caller.
        return _Context(qname, ctx.caller, True)

    def _define_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, ctx: _Context) -> _Context:
        qname = f"{ctx.scope}.{node.name}"
        self.symbols.append(
            SymbolNode(
                qualified_name=qname,
                name=node.name,
                kind=SymbolKind.METHOD if ctx.in_class else SymbolKind.FUNCTION,
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                docstring=ast.get_docstring(node) or "",
            )
        )
        return _Context(qname, qname, False)

    def _record_import(self, node: ast.Import | ast.ImportFrom, symbol: str, alias: ast.alias) -> None:
        self.imports.append(
            ImportEdge(
                importer_module=self.module_name,
                imported_symbol=symbol,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                alias=alias.asname or "",
            )
        )

    def _record_call(self, node: ast.Call, caller: str) -> None:
        callee = self._resolve_name(node.func)
        if not callee:
            return
        site = CallSite(
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            end_line=node.end_lineno or node.lineno,
            end_col=node.end_col_offset or node.col_offset,
            arg_count=len(node.args),
            kwarg_names=[kw.arg for kw in node.keywords if kw.arg is not None],
        )
        self.calls.append(CallEdge(caller=caller, callee=callee, call_site=site))

    def _resolve_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._resolve_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        return ""
