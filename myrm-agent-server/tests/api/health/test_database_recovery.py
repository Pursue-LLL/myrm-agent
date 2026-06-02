import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database.recovery import backup_database, rescue_database, restore_from_backup
from app.server.status import system_status


@pytest.fixture
def app() -> FastAPI:
    from app.main import app as main_app
    return main_app

@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)

@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    db_file = tmp_path / "test_data.db"
    
    # 初始化一个正常的数据库
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test_table (name) VALUES ('test1')")
    conn.execute("INSERT INTO test_table (name) VALUES ('test2')")
    conn.commit()
    conn.close()
    
    yield str(db_file)
    
    # 清理
    if db_file.exists():
        db_file.unlink()
    bak_file = db_file.with_suffix(".db.bak")
    if bak_file.exists():
        bak_file.unlink()


def test_backup_database(temp_db_path: str):
    """测试备份功能"""
    backup_database(temp_db_path)
    
    bak_path = Path(temp_db_path).with_suffix(".db.bak")
    assert bak_path.exists()
    
    # 验证备份内容
    conn = sqlite3.connect(str(bak_path))
    cursor = conn.execute("SELECT count(*) FROM test_table")
    assert cursor.fetchone()[0] == 2
    conn.close()


def test_rescue_database_malformed(temp_db_path: str):
    """测试损坏数据库的抢救功能"""
    # 故意破坏数据库文件头部
    with open(temp_db_path, "r+b") as f:
        f.seek(100)
        f.write(b"CORRUPTED_DATA_HERE_TO_BREAK_SQLITE")
        
    # 尝试抢救
    success = rescue_database(temp_db_path)
    
    # 抢救可能成功（如果损坏不严重），也可能失败。
    # 对于完全破坏头部的，可能抢救失败，但函数不能抛出异常。
    assert isinstance(success, bool)


def test_restore_from_backup(temp_db_path: str):
    """测试从备份恢复功能"""
    # 先备份
    backup_database(temp_db_path)
    
    # 修改原数据库
    conn = sqlite3.connect(temp_db_path)
    conn.execute("INSERT INTO test_table (name) VALUES ('test3')")
    conn.commit()
    conn.close()
    
    # 从备份恢复
    success = restore_from_backup(temp_db_path)
    assert success is True
    
    # 验证恢复内容
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.execute("SELECT count(*) FROM test_table")
    assert cursor.fetchone()[0] == 2  # 恢复到了备份时的 2 条记录
    conn.close()


@pytest.mark.asyncio
async def test_reset_database_api(client: TestClient):
    """测试重置数据库 API"""
    # 模拟降级状态
    system_status.database_degraded = True
    
    response = client.post("/api/v1/health/database/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # 验证状态已重置
    assert system_status.database_degraded is False
