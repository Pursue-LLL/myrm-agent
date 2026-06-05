import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.types import ModelConfig
from app.database.models import ApprovalRecord
from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from app.services.agent.evolution.engine import _run_evolution_task


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_run_evolution_task_e2e_no_mocks():
    """真实端到端测试，无任何 Mock。写入真实 DB 测试全链路大模型技能提取。"""
    chat_id = "test-chat-" + uuid.uuid4().hex[:6]

    basic_model = os.environ.get("BASIC_MODEL", "openai/gpt-4o-mini")
    provider_name = basic_model.split("/", 1)[0] if "/" in basic_model else "openai"
    if provider_name == "openai-compatible":
        provider_name = "openai"
        basic_model = basic_model.replace("openai-compatible/", "openai/", 1)

    model_cfg = ModelConfig(
        provider=provider_name,
        model=basic_model,
        temperature=0.0,
        api_key=os.environ.get("BASIC_API_KEY", ""),
        base_url=os.environ.get("BASIC_BASE_URL", ""),
    )

    now = datetime.now(timezone.utc)
    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(id=chat_id, title="Extract Emails Test")
        db.add(chat)

        msgs = [
            Message(
                id=uuid.uuid4().hex,
                chat_id=chat_id,
                role="user",
                content="I need to recursively find all .py files in my project, extract any TODO comments, and save them to a markdown file.",
                sent_at=now,
                sent_timezone="UTC",
            ),
            Message(
                id=uuid.uuid4().hex,
                chat_id=chat_id,
                role="assistant",
                content="I can help with that. Let's create a reusable python script to do this.\\n\\n```python\\nimport os, re\\n\\ndef find_todos():\\n    todos = []\\n    for root, _, files in os.walk('.'):\\n        for f in files:\\n            if f.endswith('.py'):\\n                with open(os.path.join(root, f), 'r') as file:\\n                    for i, line in enumerate(file):\\n                        if 'TODO' in line:\\n                            todos.append(f'- {f}:{i+1}: {line.strip()}')\\n    with open('todos.md', 'w') as out:\\n        out.write('\\n'.join(todos))\\n\\nfind_todos()\\n```\\n\\nI have successfully executed this tool and saved the results to `todos.md`.",
                sent_at=now,
                sent_timezone="UTC",
            ),
            Message(
                id=uuid.uuid4().hex,
                chat_id=chat_id,
                role="user",
                content="Perfect, the todos.md file looks exactly like what I wanted. This is a very useful process.",
                sent_at=now,
                sent_timezone="UTC",
            ),
            Message(
                id=uuid.uuid4().hex,
                chat_id=chat_id,
                role="assistant",
                content="I'm glad it worked! I have successfully completed the complex multi-step task of finding and extracting TODOs.",
                sent_at=now,
                sent_timezone="UTC",
            ),
        ]
        db.add_all(msgs)
        await db.commit()

    await _run_evolution_task(chat_id, model_cfg)

    async with session_factory() as db:
        result = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        approvals = result.scalars().all()

        assert len(approvals) >= 1, "Should have created at least 1 ApprovalRecord for evolution."
        approval = approvals[-1]

        assert isinstance(approval.payload, dict)
        assert approval.payload.get("evolution_type") == "captured"
        evolved = approval.payload.get("evolved_content", "")
        assert "todo" in evolved.lower() or "python" in evolved.lower()

        for a in approvals:
            await db.delete(a)
        for msg in msgs:
            await db.delete(msg)
        await db.delete(chat)
        await db.commit()
