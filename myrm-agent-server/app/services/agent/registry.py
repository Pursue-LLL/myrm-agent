import logging
import weakref

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Global registry for active agents using weak references to prevent memory leaks."""

    _agents: dict[str, weakref.ReferenceType[object]] = {}

    @classmethod
    def register(cls, message_id: str, agent: object) -> None:
        cls._agents[message_id] = weakref.ref(agent)
        logger.debug("Registered agent for message_id: %s", message_id)

    @classmethod
    def get_agent(cls, message_id: str) -> object | None:
        ref = cls._agents.get(message_id)
        if ref:
            agent = ref()
            if agent is not None:
                return agent
            cls._agents.pop(message_id, None)
        return None

    @classmethod
    def unregister(cls, message_id: str) -> None:
        cls._agents.pop(message_id, None)
        logger.debug("Unregistered agent for message_id: %s", message_id)
