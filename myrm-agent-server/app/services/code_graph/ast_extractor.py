"""
@input: 接收源代码文件与 AST 解析请求
@output: 针对 Python 与 TypeScript/JavaScript 文件的 AST 符号、调用关系抽取器
@pos: 代码图谱静态 AST 解析核心
"""

import ast
import re
from pathlib import Path

from app.services.code_graph.models import (
    CallEdge,
    CallSite,
    ImportEdge,
    InheritanceEdge,
    SymbolKind,
    SymbolNode,
)


class PythonAstExtractor:
    """基于 Python 3.13 原生 ast 模块的高性能静态分析抽取器。"""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.module_name = self._compute_module_name(file_path)

        self.symbols: list[SymbolNode] = []
        self.calls: list[CallEdge] = []
        self.inheritances: list[InheritanceEdge] = []
        self.imports: list[ImportEdge] = []

    def _compute_module_name(self, file_path: str) -> str:
        p = Path(file_path)
        parts = list(p.with_suffix("").parts)
        if parts and parts[0] in (".", "/"):
            parts = parts[1:]
        return ".".join(parts) if parts else p.stem

    def extract(self) -> None:
        try:
            tree = ast.parse(self.source_code, filename=self.file_path)
        except SyntaxError:
            return

        # 1. 注册 Module 根节点
        module_doc = ast.get_docstring(tree) or ""
        self.symbols.append(
            SymbolNode(
                qualified_name=self.module_name,
                name=self.module_name.split(".")[-1],
                kind=SymbolKind.MODULE,
                file_path=self.file_path,
                line_start=1,
                line_end=len(self.lines) if self.lines else 1,
                docstring=module_doc,
                source="",
            )
        )

        # 2. 遍历 AST 提取 Class, Function, Method, Import, Call
        self._visit_node(tree, current_scope=self.module_name)

    def _get_source_slice(self, node: ast.AST) -> str:
        if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(self.lines[start:end])
        return ""

    def _visit_node(self, node: ast.AST, current_scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                cls_qname = f"{current_scope}.{child.name}"
                doc = ast.get_docstring(child) or ""
                self.symbols.append(
                    SymbolNode(
                        qualified_name=cls_qname,
                        name=child.name,
                        kind=SymbolKind.CLASS,
                        file_path=self.file_path,
                        line_start=child.lineno,
                        line_end=child.end_lineno or child.lineno,
                        docstring=doc,
                        source=self._get_source_slice(child),
                    )
                )
                for base in child.bases:
                    base_name = self._resolve_name(base)
                    if base_name:
                        self.inheritances.append(
                            InheritanceEdge(
                                sub_type=cls_qname,
                                super_type=base_name,
                                file_path=self.file_path,
                                line=child.lineno,
                            )
                        )
                self._visit_node(child, current_scope=cls_qname)

            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = SymbolKind.METHOD if "." in current_scope and current_scope != self.module_name else SymbolKind.FUNCTION
                fn_qname = f"{current_scope}.{child.name}"
                doc = ast.get_docstring(child) or ""
                self.symbols.append(
                    SymbolNode(
                        qualified_name=fn_qname,
                        name=child.name,
                        kind=kind,
                        file_path=self.file_path,
                        line_start=child.lineno,
                        line_end=child.end_lineno or child.lineno,
                        docstring=doc,
                        source=self._get_source_slice(child),
                    )
                )
                # 遍历函数体内部提取 Calls
                self._extract_calls_in_function(child, caller_qname=fn_qname)
                # 支持嵌套函数
                self._visit_node(child, current_scope=fn_qname)

            elif isinstance(child, ast.Import):
                for alias in child.names:
                    self.imports.append(
                        ImportEdge(
                            importer_module=self.module_name,
                            imported_symbol=alias.name,
                            file_path=self.file_path,
                            line=child.lineno,
                            col=child.col_offset,
                            alias=alias.asname or "",
                        )
                    )

            elif isinstance(child, ast.ImportFrom):
                mod = child.module or ""
                for alias in child.names:
                    full_sym = f"{mod}.{alias.name}" if mod else alias.name
                    self.imports.append(
                        ImportEdge(
                            importer_module=self.module_name,
                            imported_symbol=full_sym,
                            file_path=self.file_path,
                            line=child.lineno,
                            col=child.col_offset,
                            alias=alias.asname or "",
                        )
                    )

    def _extract_calls_in_function(self, fn_node: ast.AST, caller_qname: str) -> None:
        for node in ast.walk(fn_node):
            if isinstance(node, ast.Call):
                callee_name = self._resolve_name(node.func)
                if callee_name:
                    kw_names = [kw.arg for kw in node.keywords if kw.arg is not None]
                    site = CallSite(
                        file_path=self.file_path,
                        line=node.lineno,
                        col=node.col_offset,
                        end_line=node.end_lineno or node.lineno,
                        end_col=node.end_col_offset or node.col_offset,
                        arg_count=len(node.args),
                        kwarg_names=kw_names,
                    )
                    self.calls.append(
                        CallEdge(
                            caller=caller_qname,
                            callee=callee_name,
                            call_site=site,
                        )
                    )

    def _resolve_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._resolve_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        return ""


class JsTsRegexExtractor:
    """针对 TypeScript/JavaScript/TSX 源码的轻量确定性符号与调用抽取器。"""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.module_name = self._compute_module_name(file_path)

        self.symbols: list[SymbolNode] = []
        self.calls: list[CallEdge] = []
        self.inheritances: list[InheritanceEdge] = []
        self.imports: list[ImportEdge] = []

    def _compute_module_name(self, file_path: str) -> str:
        p = Path(file_path)
        return p.stem

    def extract(self) -> None:
        # 1. Module
        self.symbols.append(
            SymbolNode(
                qualified_name=self.module_name,
                name=self.module_name,
                kind=SymbolKind.MODULE,
                file_path=self.file_path,
                line_start=1,
                line_end=len(self.lines) if self.lines else 1,
            )
        )

        # 2. 正则提取 class, interface, function, method
        fn_pattern = re.compile(
            r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(",
            re.MULTILINE,
        )
        const_fn_pattern = re.compile(
            r"^(?:export\s+)?const\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
            re.MULTILINE,
        )
        cls_pattern = re.compile(
            r"^(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_$]+)(?:\s+extends\s+([A-Za-z0-9_$]+))?",
            re.MULTILINE,
        )

        for i, line in enumerate(self.lines, start=1):
            cls_match = cls_pattern.search(line)
            if cls_match:
                cls_name = cls_match.group(1)
                super_cls = cls_match.group(2)
                cls_qname = f"{self.module_name}.{cls_name}"
                self.symbols.append(
                    SymbolNode(
                        qualified_name=cls_qname,
                        name=cls_name,
                        kind=SymbolKind.CLASS,
                        file_path=self.file_path,
                        line_start=i,
                        line_end=i,
                    )
                )
                if super_cls:
                    self.inheritances.append(
                        InheritanceEdge(
                            sub_type=cls_qname,
                            super_type=super_cls,
                            file_path=self.file_path,
                            line=i,
                        )
                    )
                continue

        # 3. 提取调用点 (Calls)
        call_pattern = re.compile(
            r"(?:([A-Za-z0-9_$]+)\.)?([A-Za-z0-9_$]+)\s*\(",
        )

        current_fn = self.module_name
        for i, line in enumerate(self.lines, start=1):
            fn_match = fn_pattern.search(line) or const_fn_pattern.search(line)
            if fn_match:
                current_fn = f"{self.module_name}.{fn_match.group(1)}"

            # 扫描函数调用
            stripped = line.strip()
            if not stripped.startswith("//") and not stripped.startswith("/*") and not stripped.startswith("*"):
                for m in call_pattern.finditer(line):
                    prefix = m.group(1)
                    callee = m.group(2)
                    if callee in ("function", "if", "for", "while", "switch", "catch", "return", "import"):
                        continue
                    full_callee = f"{prefix}.{callee}" if prefix else callee
                    self.calls.append(
                        CallEdge(
                            caller=current_fn,
                            callee=full_callee,
                            call_site=CallSite(
                                file_path=self.file_path,
                                line=i,
                                col=m.start(),
                                end_line=i,
                                end_col=m.end(),
                            ),
                        )
                    )

        # 3. 提取调用点（calls）
        call_pattern = re.compile(r"(?:^|[^\w$])([A-Za-z0-9_$]+)\s*\(")
        for i, line in enumerate(self.lines, start=1):
            for match in call_pattern.finditer(line):
                callee_name = match.group(1)
                if callee_name in ("function", "if", "for", "while", "switch", "catch", "return", "import", "export"):
                    continue
                site = CallSite(
                    file_path=self.file_path,
                    line=i,
                    col=match.start(1),
                    end_line=i,
                    end_col=match.end(1),
                )
                self.calls.append(
                    CallEdge(
                        caller=self.module_name,
                        callee=callee_name,
                        call_site=site,
                    )
                )
