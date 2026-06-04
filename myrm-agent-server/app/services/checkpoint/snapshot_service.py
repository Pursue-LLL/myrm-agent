import asyncio
import logging
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.interceptor import ExecutionInterceptor

logger = logging.getLogger(__name__)

# Global lock to prevent concurrent git operations per workspace
_workspace_locks: dict[str, asyncio.Lock] = {}

def _get_workspace_lock(workspace_path: str) -> asyncio.Lock:
    if workspace_path not in _workspace_locks:
        _workspace_locks[workspace_path] = asyncio.Lock()
    return _workspace_locks[workspace_path]

class SnapshotInterceptor(ExecutionInterceptor):
    """Intercepts destructive actions to create Git-based file system snapshots."""
    
    def __init__(self):
        # Keeps track of which turn_id has been snapshotted per workspace
        # Format: {(workspace_path, turn_id): True}
        self._snapshotted_turns: dict[tuple[str, str], bool] = {}
        
    async def before_destructive_action(self, workspace_path: str, action_type: str, payload: dict) -> None:
        """Called by Harness before a destructive action is executed."""
        session_id = payload.get("session_id")
        if not session_id:
            return
            
        # In a real implementation, we would extract turn_id, chat_id, agent_id from the session context.
        # For now, we use a simplified turn_id extraction or fallback to session_id.
        # This requires integration with the Agent loop context.
        from app.ai_agents.general_agent.context import get_current_turn_id, get_current_chat_id, get_current_agent_id
        
        turn_id = get_current_turn_id() or "unknown_turn"
        chat_id = get_current_chat_id() or "unknown_chat"
        agent_id = get_current_agent_id() or "unknown_agent"
        
        cache_key = (workspace_path, turn_id)
        
        # Fast path: already snapshotted this turn
        if self._snapshotted_turns.get(cache_key):
            return
            
        lock = _get_workspace_lock(workspace_path)
        async with lock:
            # Double check after acquiring lock
            if self._snapshotted_turns.get(cache_key):
                return
                
            try:
                await self._create_snapshot(workspace_path, action_type, chat_id, agent_id, turn_id)
                self._snapshotted_turns[cache_key] = True
                
                # Emit WebSocket event for UI
                await self._emit_snapshot_event(chat_id, action_type)
            except Exception as e:
                logger.error(f"Failed to create snapshot for {workspace_path}: {e}")
                # We don't raise here to avoid blocking the main execution flow

    async def _create_snapshot(self, workspace_path: str, action_type: str, chat_id: str, agent_id: str, turn_id: str) -> None:
        """Create a Git commit in the shadow repository."""
        wp = Path(workspace_path)
        if not wp.exists() or not wp.is_dir():
            return
            
        # Hard limit: skip if too many files (prevent OOM)
        # In a real implementation, we'd use a faster way to count files or rely on git's own limits
        
        # Ensure .gitignore exists and ignores large files/dirs
        gitignore_path = wp / ".gitignore"
        ignore_content = ""
        if gitignore_path.exists():
            ignore_content = gitignore_path.read_text(errors="ignore")
            
        added_rules = False
        for rule in ["node_modules/", ".venv/", "*.mp4", "*.sqlite", "*.db"]:
            if rule not in ignore_content:
                ignore_content += f"\n{rule}"
                added_rules = True
                
        if added_rules:
            gitignore_path.write_text(ignore_content.strip() + "\n")
            
        # Initialize git if needed
        git_dir = wp / ".git"
        if not git_dir.exists():
            await self._run_async_cmd("git", "init", cwd=str(wp))
            # Configure local git user
            await self._run_async_cmd("git", "config", "user.name", "Myrm Agent", cwd=str(wp))
            await self._run_async_cmd("git", "config", "user.email", "agent@myrm.ai", cwd=str(wp))
            
        # Add and commit
        await self._run_async_cmd("git", "add", ".", cwd=str(wp))
        
        # Check if there are changes to commit
        status_stdout, _ = await self._run_async_cmd("git", "status", "--porcelain", cwd=str(wp))
        if not status_stdout.strip():
            return # No changes to snapshot
            
        commit_msg = f"Auto snapshot before {action_type}\n\nChat: {chat_id}\nAgent: {agent_id}\nTurn: {turn_id}"
        await self._run_async_cmd("git", "commit", "-m", commit_msg, cwd=str(wp))
        logger.info(f"Created file system snapshot for turn {turn_id} in {workspace_path}")

    async def _run_async_cmd(self, *args: str, cwd: str) -> tuple[str, str]:
        """Run a shell command asynchronously to avoid blocking the event loop."""
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Command {' '.join(args)} failed: {stderr.decode()}")
        return stdout.decode(), stderr.decode()

    async def _emit_snapshot_event(self, chat_id: str, action_type: str) -> None:
        """Emit a WebSocket event to the frontend to show the Snapshotting UI indicator."""
        # For now, we log it. In a full implementation, we would broadcast this via the WebSocket hub
        # to the specific chat_id so the frontend can display a shield/camera icon.
        logger.info(f"SNAPSHOT_EVENT: chat_id={chat_id}, action={action_type}, message='Creating snapshot backup'")
