"""Unit tests for CodeGraphService and multi-language AST extractors."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.code_graph.ast_extractor import JsTsRegexExtractor, PythonAstExtractor
from app.services.code_graph.service import CodeGraphService


def test_python_ast_extractor():
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



def test_jsts_regex_extractor():
    sample_ts = """
export class AuthService extends BaseAuth {
  async login(token: string) {
    return true;
  }
}

export function validateInput(val: string) {
  if (val.length > 0) {
    checkToken(val);
  }
  return val.length > 0;
}
"""
    extractor = JsTsRegexExtractor("auth.ts", sample_ts)
    extractor.extract()

    symbols = {s.qualified_name: s for s in extractor.symbols}
    assert "auth.AuthService" in symbols
    assert "auth.validateInput" in symbols
    assert len(extractor.inheritances) == 1
    assert extractor.inheritances[0].super_type == "BaseAuth"
    assert len(extractor.calls) >= 1
    callee_names = [c.callee for c in extractor.calls]
    assert "checkToken" in callee_names


def test_code_graph_service_e2e():
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
        caller_names = [c["caller"] for c in callers]
        assert any("process_order" in c for c in caller_names)

        # 3. 验证 tests_reaching 拓扑触达
        reaching = service.tests_reaching("core_calculator")
        assert len(reaching) >= 1
        assert any("test_order_flow" in r["test_symbol"] for r in reaching)
        assert any("test_service.py" in r["file_path"] for r in reaching)

        # 4. 验证增量 reingest
        svc_file.write_text(
            """
def core_calculator(x: int) -> int:
    return x * 3

def new_caller(x: int):
    return core_calculator(x)
""",
            encoding="utf-8",
        )
        reingest_res = service.reingest_file(root_path, "app/service.py")
        assert reingest_res["status"] == "updated"

        new_callers = service.callers("core_calculator")
        new_caller_names = [c["caller"] for c in new_callers]
        assert any("new_caller" in c for c in new_caller_names)
        assert not any("process_order" in c for c in new_caller_names)
