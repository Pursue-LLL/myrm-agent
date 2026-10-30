"""Unit tests for CodeGraphService and the Python extractor."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.code_graph.ast_extractor import PythonAstExtractor
from app.services.code_graph.models import SymbolKind
from app.services.code_graph.service import CodeGraphService


def test_python_ast_extractor() -> None:
    sample_code = """
class BaseService:
    def execute(self):
        pass

class UserService(BaseService):
    def get_user(self, user_id: str):
        return self.verify(user_id)

    def verify(self, uid):
        return True

def standalone_helper():
    s = UserService()
    s.get_user("123")
"""
    extractor = PythonAstExtractor("services/user.py", sample_code)
    extractor.extract()

    # 验证模块与类
    symbols = {s.qualified_name: s for s in extractor.symbols}
    assert "services.user" in symbols
    assert "services.user.BaseService" in symbols
    assert "services.user.UserService" in symbols
    assert "services.user.UserService.get_user" in symbols

    # 验证继承
    assert len(extractor.inheritances) == 1
    assert extractor.inheritances[0].sub_type == "services.user.UserService"
    assert extractor.inheritances[0].super_type == "BaseService"

    # 验证调用
    callers = [c.caller for c in extractor.calls]
    assert "services.user.UserService.get_user" in callers
    assert "services.user.standalone_helper" in callers


def test_code_graph_service_indexes_typescript_functions(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "auth.ts").write_text(
        "export function validateInput(val: string) {\n  return val.length > 0;\n}\n",
        encoding="utf-8",
    )
    service = CodeGraphService(tmp_path / "graph.db")

    service.index_directory(root)

    definition = service.definition("auth.validateInput")
    assert definition is not None
    assert (definition["kind"], definition["file_path"], definition["line_start"]) == ("function", "auth.ts", 1)
    assert [r["qualified_name"] for r in service.resolve("auth.ts:1")][0] == "auth.validateInput"


def test_code_graph_service_returns_each_typescript_call_once(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "auth.ts").write_text(
        "export function validateInput(val: string) {\n  checkToken(val);\n}\n",
        encoding="utf-8",
    )
    service = CodeGraphService(tmp_path / "graph.db")

    service.index_directory(root)

    assert [(c["caller"], c["line"]) for c in service.callers("checkToken")] == [("auth.validateInput", 2)]


def test_code_graph_service_e2e() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root_path = Path(tmp_dir)
        src_dir = root_path / "app"
        tests_dir = root_path / "tests"
        src_dir.mkdir()
        tests_dir.mkdir()

        # 写入源码
        svc_file = src_dir / "service.py"
        svc_file.write_text(
            """
def core_calculator(x: int) -> int:
    return x * 2

def process_order(x: int):
    return core_calculator(x)
""",
            encoding="utf-8",
        )

        # 写入测试
        test_file = tests_dir / "test_service.py"
        test_file.write_text(
            """
from app.service import process_order

def test_order_flow():
    assert process_order(10) == 20
""",
            encoding="utf-8",
        )

        db_path = root_path / "code_graph.db"
        service = CodeGraphService(db_path)

        # 1. 扫描构建全量索引
        stats = service.index_directory(root_path)
        assert stats.total_files == 2
        assert stats.total_symbols >= 4

        # 2. 验证 callers
        callers = service.callers("core_calculator")
        assert len(callers) >= 1
        caller_names = [str(c["caller"]) for c in callers]
        assert any("process_order" in c for c in caller_names)

        # 3. 验证 tests_calling 只报告直接调用目标的测试
        calling = service.tests_calling("process_order")
        assert [(r["test_symbol"], r["file_path"]) for r in calling] == [
            ("tests.test_service.test_order_flow", "tests/test_service.py")
        ]
        assert service.tests_calling("core_calculator") == []

        # 4. 验证增量同步：只重新解析改动的文件
        svc_file.write_text(
            """
def core_calculator(x: int) -> int:
    return x * 3

def new_caller(x: int):
    return core_calculator(x)
""",
            encoding="utf-8",
        )
        refresh = service.index_directory(root_path)
        assert (refresh.updated_files, refresh.removed_files) == (1, 0)

        new_callers = service.callers("core_calculator")
        new_caller_names = [str(c["caller"]) for c in new_callers]
        assert any("new_caller" in c for c in new_caller_names)
        assert not any("process_order" in c for c in new_caller_names)


def test_index_directory_ignores_excluded_names_above_the_scan_root(tmp_path: Path) -> None:
    """A workspace that lives under a directory named like an excluded one is still indexed."""
    root = tmp_path / "build" / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    stats = CodeGraphService(tmp_path / "graph.db").index_directory(root)

    assert stats.total_files == 1


def test_index_directory_skips_excluded_directories_inside_the_scan_root(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    for rel in ("keep.py", "node_modules/dep.js", "dist/out.js", ".venv/lib.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")

    stats = CodeGraphService(tmp_path / "graph.db").index_directory(root)

    assert stats.total_files == 1


_PYTHON_CONTEXTS = """import os
try:
    import ujson
except ImportError:
    ujson = None
if TYPE_CHECKING:
    from shapes import Circle

def create_app():
    return 1

app = create_app()

if __name__ == "__main__":
    main()

@router.get("/x")
def handler():
    def inner():
        helper()
    return inner

class A:
    attr = make()
    def method(self):
        def nested():
            pass
        return nested

if sys.platform == "win32":
    def win_only():
        pass
"""


def test_python_calls_outside_functions_belong_to_the_module_and_each_call_has_one_caller() -> None:
    extractor = PythonAstExtractor("m.py", _PYTHON_CONTEXTS)
    extractor.extract()

    pairs = sorted((c.callee, c.caller) for c in extractor.calls)
    assert pairs == [
        ("create_app", "m"),
        ("helper", "m.handler.inner"),
        ("main", "m"),
        ("make", "m"),
        ("router.get", "m"),
    ]


def test_python_definitions_and_imports_are_found_inside_compound_statements() -> None:
    extractor = PythonAstExtractor("m.py", _PYTHON_CONTEXTS)
    extractor.extract()

    assert "m.win_only" in {s.qualified_name for s in extractor.symbols}
    assert {i.imported_symbol for i in extractor.imports} == {"os", "ujson", "shapes.Circle"}


def test_only_functions_defined_directly_in_a_class_are_methods() -> None:
    extractor = PythonAstExtractor("m.py", _PYTHON_CONTEXTS)
    extractor.extract()

    kinds = {s.qualified_name: s.kind for s in extractor.symbols}
    assert kinds["m.A.method"] == SymbolKind.METHOD
    assert kinds["m.A.method.nested"] == SymbolKind.FUNCTION
    assert kinds["m.handler.inner"] == SymbolKind.FUNCTION
    assert kinds["m.win_only"] == SymbolKind.FUNCTION


def test_python_walk_handles_an_expression_nested_deeper_than_the_recursion_limit() -> None:
    extractor = PythonAstExtractor("m.py", "x = " + " + ".join(["f()"] * 3000) + "\n")

    assert extractor.extract() is True
    assert len(extractor.calls) == 3000


def test_resolve_by_location_prefers_a_symbol_over_the_module_that_spans_the_same_lines(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "solo.ts").write_text("export function solo() {\n  return 1;\n}\n", encoding="utf-8")
    (root / "lone.py").write_text("def lone():\n    return 1\n", encoding="utf-8")
    service = CodeGraphService(tmp_path / "graph.db")

    service.index_directory(root)

    assert [r["qualified_name"] for r in service.resolve("solo.ts:2")] == ["solo.solo", "solo"]
    assert [r["qualified_name"] for r in service.resolve("lone.py:2")] == ["lone.lone", "lone"]
