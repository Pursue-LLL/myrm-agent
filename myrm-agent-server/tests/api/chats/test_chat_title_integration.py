import os
import pytest
import asyncio
from fastapi.testclient import TestClient
from app.database.dto import MessageDTO
from datetime import datetime
from app.main import app

@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 50000))

@pytest.fixture(autouse=True)
def setup_test_config():
    from app.database.connection import get_session_factory
    from app.database.models.config import UserConfig
    from sqlalchemy import delete
    
    async def _setup():
        session_factory = get_session_factory()
        async with session_factory() as session:
            await session.execute(delete(UserConfig))
            
            basic_model = os.environ.get("BASIC_MODEL", "gpt-4o")
            basic_key = os.environ.get("BASIC_API_KEY", "test-key")
            basic_url = os.environ.get("BASIC_BASE_URL", "")
            
            providers_dict = {
                "defaultModelConfig": {
                    "providerId": "test-provider",
                    "model": basic_model
                },
                "providers": [
                    {
                        "id": "test-provider",
                        "providerType": "openai",
                        "isEnabled": True,
                        "apiUrl": basic_url,
                        "apiKeys": [{"key": basic_key, "isActive": True}],
                        "enabledModels": [basic_model],
                    }
                ]
            }
            
            config = UserConfig(
                id="test-config-1",
                config_key="providers",
                config_value=providers_dict,
                version="1_0",
                last_device_id="test-device"
            )
            session.add(config)
            
            default_model_config = UserConfig(
                id="test-config-2",
                config_key="default_model",
                config_value={
                    "model": basic_model,
                    "api_key": basic_key,
                    "base_url": basic_url
                },
                version="1_0",
                last_device_id="test-device"
            )
            session.add(default_model_config)
            
            await session.commit()
            
    asyncio.run(_setup())

@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="Integration test requires BASIC_API_KEY environment variable",
)
class TestChatTitleIntegration:
    """聊天标题生成 E2E 测试"""

    def test_generate_chat_title_basic(self, client: TestClient):
        """测试基础的标题生成"""
        # 构造一条用户消息
        messages = [
            {
                "messageId": "msg-1",
                "chatId": "chat-1",
                "role": "user",
                "content": "帮我写一个 python 的快速排序算法",
                "sentAt": datetime.now().isoformat(),
                "sentTimezone": "UTC",
                "createdAt": datetime.now().isoformat(),
            }
        ]
        
        request_data = {
            "messages": messages
        }

        response = client.post("/api/v1/chats/generate-title", json=request_data)
        
        if response.status_code != 200:
            print(f"\nHTTP Error {response.status_code}: {response.text}")
            
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        
        title = data.get("data", {}).get("title")
        assert title is not None
        assert isinstance(title, str)
        assert len(title) > 0
        assert "python" in title.lower() or "快速排序" in title or "算法" in title

    def test_generate_chat_title_with_code_block_truncation(self, client: TestClient):
        """测试超大代码块截断后的兜底标题生成"""
        # 构造一条超大未闭合代码块消息，触发截断和兜底
        massive_code = "```python\n" + ("print('hello')\n" * 500)
        messages = [
            {
                "messageId": "msg-2",
                "chatId": "chat-2",
                "role": "user",
                "content": massive_code,
                "sentAt": datetime.now().isoformat(),
                "sentTimezone": "UTC",
                "createdAt": datetime.now().isoformat(),
            }
        ]
    
        request_data = {
            "messages": messages
        }
    
        response = client.post("/api/v1/chats/generate-title", json=request_data)
    
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        
        title = data.get("data", {}).get("title")
        assert title is not None
        # 应该触发空文本兜底
        assert title in ["Python Snippet", "Snippet", "Untitled Chat"]

    def test_generate_chat_title_with_unclosed_html(self, client: TestClient):
        """测试未闭合 HTML 标签的剥离"""
        massive_html = "<div>" + ("<p>hello</p>" * 500)
        messages = [
            {
                "messageId": "msg-3",
                "chatId": "chat-3",
                "role": "user",
                "content": massive_html,
                "sentAt": datetime.now().isoformat(),
                "sentTimezone": "UTC",
                "createdAt": datetime.now().isoformat(),
            }
        ]
        
        request_data = {
            "messages": messages
        }
        
        response = client.post("/api/v1/chats/generate-title", json=request_data)
        assert response.status_code == 200
        title = response.json().get("data", {}).get("title")
        assert title is not None
        assert "hello" in title.lower() or title in ["Snippet", "Untitled Chat"]
