"""AgentCard generator for A2A discovery.

Generates standard Google A2A v1.0 AgentCard specifications dynamically
from Myrm's Agent Profile SSOT and system configuration.

[INPUT]
- agent_id (optional), base_url

[OUTPUT]
- AgentCard: Fully qualified declarative agent manifest

[POS]
Service layer bridge between Myrm agent profile configuration
and standard A2A protocol discovery.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.a2a.types import (
    A2A_PROTOCOL_VERSION,
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    TransportProtocol,
)

from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = AgentProvider(
    organization="Myrm AI",
    url="https://myrm.ai",
)

_CORE_DEFAULT_SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="general_task_execution",
        name="General Task Execution",
        description="Autonomous multi-step reasoning, planning, and task execution.",
        tags=["general", "reasoning", "planning"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    ),
    AgentSkill(
        id="code_execution",
        name="Sandboxed Code Execution",
        description="Safe execution of Python and shell code in an isolated environment.",
        tags=["coding", "python", "sandbox"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    ),
]


class AgentCardGenerator:
    """Generates standard A2A AgentCard manifests."""

    def __init__(self, default_provider: AgentProvider | None = None) -> None:
        self.provider = default_provider or _DEFAULT_PROVIDER

    async def generate_card(
        self,
        agent_id: str | None = None,
        *,
        base_url: str = "",
    ) -> AgentCard:
        """Generate AgentCard for a specific profile or default agent."""
        clean_base = base_url.rstrip("/")

        if agent_id:
            return await self._generate_profile_card(agent_id, clean_base)

        return self._generate_default_card(clean_base)

    def _generate_default_card(self, base_url: str) -> AgentCard:
        endpoint_url = f"{base_url}/api/v1/a2a/rpc" if base_url else "/api/v1/a2a/rpc"
        return AgentCard(
            name="Myrm Agent",
            description="Autonomous general-purpose AI agent with multi-modal toolsets and sandboxed execution.",
            version="1.0.0",
            supported_interfaces=[
                AgentInterface(
                    url=endpoint_url,
                    protocol_binding=TransportProtocol.JSONRPC,
                    protocol_version=A2A_PROTOCOL_VERSION,
                )
            ],
            capabilities=AgentCapabilities(
                streaming=True,
                push_notifications=True,
            ),
            skills=_CORE_DEFAULT_SKILLS,
            provider=self.provider,
        )

    async def _generate_profile_card(self, agent_id: str, base_url: str) -> AgentCard:
        resolver = get_agent_profile_resolver()
        try:
            profile = await resolver.resolve(agent_id)
        except Exception as e:
            logger.warning("Could not resolve profile %s, falling back to default card: %s", agent_id, e)
            profile = None

        if profile is None:
            # Fallback for unrecognized profile id with explicit agent URL
            endpoint_url = (
                f"{base_url}/api/v1/a2a/agents/{agent_id}/rpc"
                if base_url
                else f"/api/v1/a2a/agents/{agent_id}/rpc"
            )
            return AgentCard(
                name=f"Agent-{agent_id}",
                description=f"Specialist agent instance for {agent_id}.",
                version="1.0.0",
                supported_interfaces=[
                    AgentInterface(
                        url=endpoint_url,
                        protocol_binding=TransportProtocol.JSONRPC,
                        protocol_version=A2A_PROTOCOL_VERSION,
                    )
                ],
                capabilities=AgentCapabilities(
                    streaming=True,
                    push_notifications=True,
                ),
                skills=_CORE_DEFAULT_SKILLS,
                provider=self.provider,
            )

        endpoint_url = (
            f"{base_url}/api/v1/a2a/agents/{agent_id}/rpc"
            if base_url
            else f"/api/v1/a2a/agents/{agent_id}/rpc"
        )

        skills: list[AgentSkill] = []
        for s_id in profile.skill_ids:
            skills.append(
                AgentSkill(
                    id=s_id,
                    name=s_id.replace("_", " ").title(),
                    description=f"Specialist skill {s_id} configured on this agent profile.",
                    tags=["specialist", s_id],
                    input_modes=["text/plain"],
                    output_modes=["text/plain"],
                )
            )

        # Include core execution skills if no explicit skills defined
        if not skills:
            skills = list(_CORE_DEFAULT_SKILLS)

        desc = (
            profile.system_prompt[:200]
            if profile.system_prompt
            else f"Specialist agent {agent_id} with {len(skills)} declared skills."
        )

        return AgentCard(
            name=f"Myrm-{agent_id}",
            description=desc,
            version="1.0.0",
            supported_interfaces=[
                AgentInterface(
                    url=endpoint_url,
                    protocol_binding=TransportProtocol.JSONRPC,
                    protocol_version=A2A_PROTOCOL_VERSION,
                )
            ],
            capabilities=AgentCapabilities(
                streaming=True,
                push_notifications=True,
            ),
            skills=skills,
            provider=self.provider,
        )
