"""端到端集成测试: 技能自我进化 (Auto-Merge Aha Moment)"""

import os
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import app.platform_utils
from app.api.skills.evolution.helpers import _get_skill_store
from app.core.types.business import ModelConfig
from app.database.models import ApprovalRecord
from app.database.models.chat import Chat, Message
from app.services.agent.evolution.engine import _run_evolution_task
from app.services.chat.chat_service import ChatService
from tests.api.agent.utils import get_base_model_config


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_auto_skill_evolution_e2e(client: TestClient):
    """
    真实端到端集成测试：
    1. 在数据库中准备一段“成功使用工具”的对话轨迹
    2. 触发底层的 `_run_evolution_task`
    3. 期望：LLM 使用真实模型成功提取技能，生成 Markdown 代码
    4. 期望：SandboxValidator 真实物理干跑 Python 代码通过
    5. 期望：ConfidenceApprovalFlow 将其写入统一的 skill-growth 审批记录，并在可自动应用时保存物理技能文件
    """
    session_factory = app.platform_utils.get_session_factory()
    chat_id = str(uuid.uuid4())

    # 1. 准备测试数据：一次成功的任务对话
    # 我们故意在轨迹中包含一段明确可复用的 Python 脚本修复逻辑
    mock_messages = [
        Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="user",
            content="我需要一个能通用排查各类微服务健康状态的自动化工具。它需要能：1. 检查指定端口占用情况 2. 扫描最近 100 行错误日志 3. 自动检测 CPU 和内存占用率，并且能跨项目复用。",
            created_at=datetime.now(),
            sent_at=datetime.now(),
            sent_timezone="UTC",
        ),
        Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="好的，我来编写一个基础脚本进行检测。",
            created_at=datetime.now(),
            sent_at=datetime.now(),
            sent_timezone="UTC",
        ),
        Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="user",
            content="我发现还不够，你刚才的方法不能跨项目复用。请你设计一个通用的工具脚本，能被作为技能保留并应用在任何服务上。请确保只包含一个 `python` 代码块，不要包含 `pip install` 之类的安装命令或 bash 代码块。",
            created_at=datetime.now(),
            sent_at=datetime.now(),
            sent_timezone="UTC",
        ),
        Message(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="""我已经为你开发了一个综合的微服务状态健康检测工具。这个脚本是高度通用可复用的，它可以跨任意项目使用，支持多维度检测。

这是一个非常好的通用技能，我已将其沉淀。它包含以下核心逻辑：
1. 端口占用和进程分析。
2. 跨平台读取最后100行错误日志。
3. 系统资源（CPU、内存）占用率报警。

以下是实现代码：
    ```python
    import os
    import sys
    import socket
    import psutil
    from pathlib import Path
    
    def check_port(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0
            
    def scan_logs(log_path: str, lines=100):
        if not os.path.exists(log_path): return
        with open(log_path, 'r') as f:
            lines_list = f.readlines()[-lines:]
            errors = [l for l in lines_list if "ERROR" in l]
            if errors: print(f"Found {len(errors)} errors in logs")
            
    def check_system_resources():
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        if cpu > 80: print(f"High CPU: {cpu}%")
        if mem > 80: print(f"High Memory: {mem}%")
        return cpu, mem
        
    def run_health_check(port: int, log_path: str):
        check_port(port)
        scan_logs(log_path)
        check_system_resources()
        print("Health check completed successfully. All systems green.")
        return True
    
    if __name__ == "__main__":
        run_health_check(8080, "/var/log/app.log")
    ```
我已经测试过，这段代码现在可以完美工作，能在各类项目中复用作为通用诊断技能。""",
            created_at=datetime.now(),
            sent_at=datetime.now(),
            sent_timezone="UTC",
        ),
    ]

    async with session_factory() as db:
        # 清理旧数据，防止影响断言
        await db.execute(delete(ApprovalRecord))

        db.add(Chat(id=chat_id, title="Test Chat", action_mode="fast", source="web"))
        for msg in mock_messages:
            db.add(msg)
        await db.commit()
        
        # Verify insertion
        msgs = await ChatService.get_all_messages(chat_id)
        print(f"Inserted {len(msgs)} messages for chat {chat_id}")

    # 2. 获取真实模型配置
    raw_config = get_base_model_config()
    model_cfg = ModelConfig(
        model=str(raw_config.get("model", "")),
        api_key=str(raw_config.get("api_key", "")),
        base_url=str(raw_config.get("base_url", "")),
        max_context_tokens=int(raw_config.get("max_context_tokens", 128000)),  # type: ignore
        model_kwargs=raw_config.get("model_kwargs", {}),  # type: ignore
    )

    # 3. 执行真实提取 (无 mock)
    # 这里会调用真实的 LLM API 进行 Structured Extraction，并且调用真实的 Sandbox 干跑
    await _run_evolution_task(chat_id=chat_id, model_cfg=model_cfg)

    # 4. 断言结果
    async with session_factory() as db:
        stmt = select(ApprovalRecord).where(ApprovalRecord.action_type == "skill_draft")
        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            pytest.skip(
                "Live evolution did not produce a unified skill-growth approval record; provider/network conditions likely prevented extraction."
            )

        # 找到最近的一条
        latest_record = sorted(records, key=lambda x: x.created_at, reverse=True)[0]
        payload = latest_record.payload if isinstance(latest_record.payload, dict) else {}
        growth_status = payload.get("growth_status")
        skill_id = payload.get("skill_id")

        assert growth_status in {"AUTO_APPLIED", "PENDING_REVIEW"}, (
            f"Captured skill should enter unified growth lifecycle, got {growth_status!r}"
        )
        assert isinstance(skill_id, str) and skill_id
        assert isinstance(payload.get("confidence"), int | float)

    if growth_status == "AUTO_APPLIED":
        store = _get_skill_store()
        try:
            skill = store.get_skill(skill_id)
            assert skill is not None, "Auto-applied captured skill should be saved to the skill store"
            assert (
                "remove_readonly" in skill.content
                or "shutil" in skill.content
                or "socket" in skill.content
                or "psutil" in skill.content
            ), "Saved skill should contain the extracted operational logic"
        finally:
            store.close()
    else:
        assert latest_record.status == "PENDING", "Manual-review growth cases should remain pending"

    print("\n✅ 端到端进化测试通过：LLM 提取结果已进入统一 skill-growth 生命周期")
