import asyncio
import os
import sys

# Add server to path
sys.path.append(os.path.join(os.path.dirname(__file__), "myrm-agent-server"))

async def create_mock_drafts():
    from app.services.approvals.registry import ApprovalRegistry
    from app.database.connection import init_database
    
    await init_database()
    
    await ApprovalRegistry.create_approval(
        agent_id="default",
        chat_id="test_chat_123",
        action_type="skill_draft",
        payload={
            "skill_name": "test-frontend-approve",
            "description": "This is a test skill for UI Approve button.",
            "content": "```markdown\n---\nname: test-frontend-approve\ndescription: \"approve test\"\n---\n\n# Rules\nApprove rules\n```",
            "score": 0.95
        },
        reason="Test draft approve UI",
    )
    
    await ApprovalRegistry.create_approval(
        agent_id="default",
        chat_id="test_chat_123",
        action_type="skill_draft",
        payload={
            "skill_name": "test-frontend-reject",
            "description": "This is a test skill for UI Reject button.",
            "content": "```markdown\n---\nname: test-frontend-reject\ndescription: \"reject test\"\n---\n\n# Rules\nReject rules\n```",
            "score": 0.95
        },
        reason="Test draft reject UI",
    )
    
    print("Created mock drafts successfully.")

if __name__ == "__main__":
    asyncio.run(create_mock_drafts())
