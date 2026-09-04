"""
@input: 依赖 ast_extractor.py 与 graph_store.py
@output: 对外提供 8 大确定性图遍历操作及单文件增量 reingest
@pos: 代码图谱业务管理与工具服务门面
"""

import time
from pathlib import Path

from app.services.code_graph.ast_extractor import JsTsRegexExtractor, PythonAstExtractor
from app.services.code_graph.graph_store import CodeGraphStore
from app.services.code_graph.models import IndexStats


class CodeGraphService:
    """代码调用图谱核心服务：索引构建、增量更新及 8 大确定性图查询门面。"""

    EXCLUDE_DIRS = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".next",
        "dist",
        "build",
        ".cursor",
        ".cursor2",
        "temp-docs",
    }

    def __init__(self, db_path: str | Path):
        self.store = CodeGraphStore(db_path)

    def index_directory(self, root_dir: str | Path) -> IndexStats:
        """全量或首次扫描并索引目录下的 Python 与 JS/TS 源码。"""
        root = Path(root_dir)
        start_time = time.perf_counter()

        all_symbols = []
        all_calls = []
        all_inheritances = []
        all_imports = []
        processed_files = 0

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            # 排除黑名单目录
            if any(part in self.EXCLUDE_DIRS for part in path.parts):
                continue

            rel_path = str(path.relative_to(root))

            if path.suffix == ".py":
                try:
                    code = path.read_text(encoding="utf-8", errors="ignore")
                    extractor = PythonAstExtractor(rel_path, code)
                    extractor.extract()
                    all_symbols.extend(extractor.symbols)
                    all_calls.extend(extractor.calls)
                    all_inheritances.extend(extractor.inheritances)
                    all_imports.extend(extractor.imports)
                    processed_files += 1
                except Exception:
                    continue

            elif path.suffix in (".ts", ".tsx", ".js", ".jsx"):
                try:
                    code = path.read_text(encoding="utf-8", errors="ignore")
                    extractor_js = JsTsRegexExtractor(rel_path, code)
                    extractor_js.extract()
                    all_symbols.extend(extractor_js.symbols)
                    all_calls.extend(extractor_js.calls)
                    all_inheritances.extend(extractor_js.inheritances)
                    all_imports.extend(extractor_js.imports)
                    processed_files += 1
                except Exception:
                    continue

        self.store.batch_insert(all_symbols, all_calls, all_inheritances, all_imports)
        elapsed = (time.perf_counter() - start_time) * 1000.0

        return IndexStats(
            total_files=processed_files,
            total_symbols=len(all_symbols),
            total_calls=len(all_calls),
            elapsed_ms=elapsed,
        )

    def reingest_file(self, root_dir: str | Path, rel_file_path: str) -> dict[str, Any]:
        """增量重析单文件：毫秒级移除旧数据并重新提取关系。"""
        start_time = time.perf_counter()
        full_path = Path(root_dir) / rel_file_path

        # 1. 物理移除已删除或旧的记录
        self.store.delete_file_entries(rel_file_path)

        if not full_path.exists():
            return {
                "file_path": rel_file_path,
                "status": "removed",
                "elapsed_ms": (time.perf_counter() - start_time) * 1000.0,
            }

        code = full_path.read_text(encoding="utf-8", errors="ignore")
        symbols = []
        calls = []
        inhs = []
        imps = []

        if full_path.suffix == ".py":
            extractor = PythonAstExtractor(rel_file_path, code)
            extractor.extract()
            symbols = extractor.symbols
            calls = extractor.calls
            inhs = extractor.inheritances
            imps = extractor.imports
        elif full_path.suffix in (".ts", ".tsx", ".js", ".jsx"):
            extractor_js = JsTsRegexExtractor(rel_file_path, code)
            extractor_js.extract()
            symbols = extractor_js.symbols
            calls = extractor_js.calls
            inhs = extractor_js.inheritances
            imps = extractor_js.imports

        self.store.batch_insert(symbols, calls, inhs, imps)
        elapsed = (time.perf_counter() - start_time) * 1000.0

        return {
            "file_path": rel_file_path,
            "status": "updated",
            "symbols_count": len(symbols),
            "calls_count": len(calls),
            "elapsed_ms": elapsed,
        }

    # ==================== 8 大确定性图遍历操作 ====================

    def resolve(self, target: str) -> list[dict[str, Any]]:
        """1. 解析符号或 path:line 为完全限定名。"""
        return self.store.resolve_names(target)

    def definition(self, qualified_name: str) -> dict[str, Any] | None:
        """2. 获取符号的准确定义位置、文档注释与源码。"""
        node = self.store.get_symbol(qualified_name)
        return node.to_dict() if node else None

    def callers(self, callee_name: str) -> list[dict[str, Any]]:
        """3. 获取调用指定函数的所有 CallSite 位置与参数信息（纯确定性检索）。"""
        return self.store.get_callers(callee_name)

    def callees(self, caller_qname: str) -> list[dict[str, Any]]:
        """4. 获取指定函数内部调用的所有子函数。"""
        return self.store.get_callees(caller_qname)

    def implementors(self, super_type_name: str) -> list[dict[str, Any]]:
        """5. 获取继承或实现指定类/接口的所有派生类型。"""
        return self.store.get_implementors(super_type_name)

    def overrides(self, method_name: str) -> list[dict[str, Any]]:
        """6. 获取方法的重写关系。"""
        bare_name = method_name.split(".")[-1]
        callers = self.store.get_implementors(method_name)
        return [{"method": bare_name, "inheritance": item} for item in callers]

    def importers(self, module_name: str) -> list[dict[str, Any]]:
        """7. 获取导入了指定模块的所有文件及行号列号。"""
        return self.store.get_importers(module_name)

    def tests_reaching(self, target_qname: str) -> list[dict[str, Any]]:
        """8. 基于反向调用图确定受改动直接或间接影响的目标测试集。"""
        return self.store.get_tests_reaching(target_qname)
