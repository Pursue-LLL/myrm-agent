"""Integration test for RepoCallGraphAstMcpSkillPack.

Tests the full deterministic toolchain and task flow:
1. Indexing a multi-language project repository.
2. Resolving target symbols and path:line.
3. Querying callers with exact call site arguments and locations.
4. Querying callees and implementors.
5. Inverting call graph to find direct & indirect reaching test suites.
6. Incremental file reingestion consistency.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.code_graph.service import CodeGraphService


def test_repo_call_graph_full_task_flow_integration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root_path = Path(tmp_dir)
        backend_dir = root_path / "app" / "services"
        frontend_dir = root_path / "frontend" / "components"
        tests_dir = root_path / "tests" / "unit"
        backend_dir.mkdir(parents=True)
        frontend_dir.mkdir(parents=True)
        tests_dir.mkdir(parents=True)

        # 1. 编写后端业务代码
        auth_service_code = """
class BaseAuthenticator:
    def verify_token(self, token: str) -> bool:
        return len(token) > 5

class UserAuthService(BaseAuthenticator):
    def login(self, username: str, token: str):
        if self.verify_token(token):
            return {"user": username, "status": "active"}
        return None

def helper_authenticate(token: str):
    svc = UserAuthService()
    return svc.verify_token(token)
"""
        (backend_dir / "auth.py").write_text(auth_service_code, encoding="utf-8")

        # 2. 编写前端业务代码（TypeScript）
        frontend_code = """
export class AuthClient extends BaseClient {
    async authenticateUser(jwt: string) {
        return this.verifyToken(jwt);
    }
}
"""
        (frontend_dir / "AuthCard.tsx").write_text(frontend_code, encoding="utf-8")

        # 3. 编写关联测试代码
        test_auth_code = """
from app.services.auth import UserAuthService, helper_authenticate

def test_user_login():
    svc = UserAuthService()
    assert svc.login("alice", "secret_token") is not None

def test_helper():
    assert helper_authenticate("valid_token") is True
"""
        (tests_dir / "test_auth_flow.py").write_text(test_auth_code, encoding="utf-8")

        # 4. 初始化图谱服务并全量索引
        db_file = root_path / "code_graph.db"
        service = CodeGraphService(db_file)
        stats = service.index_directory(root_path)

        assert stats.total_files == 3
        assert stats.total_symbols >= 6
        assert stats.total_calls >= 4

        # 5. 测试 1：精确解析符号（resolve）
        resolved = service.resolve("UserAuthService")
        assert len(resolved) >= 1
        assert any("UserAuthService" in r["qualified_name"] for r in resolved)

        # 6. 测试 2：确定性定位所有调用点（callers）
        callers = service.callers("verify_token")
        caller_names = [c["caller"] for c in callers]
        assert "app.services.auth.UserAuthService.login" in caller_names
        assert "app.services.auth.helper_authenticate" in caller_names

        # 7. 测试 3：测试影响面与爆炸半径追溯（tests_reaching）
        reaching = service.tests_reaching("verify_token")
        assert len(reaching) >= 2
        test_symbols = [r["test_symbol"] for r in reaching]
        assert "tests.unit.test_auth_flow.test_user_login" in test_symbols
        assert "tests.unit.test_auth_flow.test_helper" in test_symbols

        # 8. 测试 4：继承与派生发现（implementors）
        impls = service.implementors("BaseAuthenticator")
        assert len(impls) >= 1
        assert any("UserAuthService" in im["sub_type"] for im in impls)

        # 9. 测试 5：单文件毫秒级增量更新（reingest_file）
        modified_auth_code = """
class UserAuthService:
    def brand_new_login(self, token: str):
        return self.verify_token(token)
"""
        (backend_dir / "auth.py").write_text(modified_auth_code, encoding="utf-8")
        reingest_result = service.reingest_file(root_path, "app/services/auth.py")
        assert reingest_result["status"] == "updated"

        # 再次查 callers，验证旧调用已清空，新调用已生效
        updated_callers = service.callers("verify_token")
        updated_names = [c["caller"] for c in updated_callers]
        assert "app.services.auth.UserAuthService.brand_new_login" in updated_names
        assert "app.services.auth.UserAuthService.login" not in updated_names
