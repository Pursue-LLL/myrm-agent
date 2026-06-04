import contextvars
from typing import Optional

_current_turn_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_turn_id", default=None)
_current_chat_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_chat_id", default=None)
_current_agent_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_agent_id", default=None)

def set_current_turn_id(turn_id: str) -> contextvars.Token:
    return _current_turn_id.set(turn_id)

def get_current_turn_id() -> Optional[str]:
    return _current_turn_id.get()

def set_current_chat_id(chat_id: str) -> contextvars.Token:
    return _current_chat_id.set(chat_id)

def get_current_chat_id() -> Optional[str]:
    return _current_chat_id.get()

def set_current_agent_id(agent_id: str) -> contextvars.Token:
    return _current_agent_id.set(agent_id)

def get_current_agent_id() -> Optional[str]:
    return _current_agent_id.get()
