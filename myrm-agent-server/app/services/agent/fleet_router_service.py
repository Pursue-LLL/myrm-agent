import time
from typing import Optional

from myrm_agent_harness.agent.sub_agents.fleet_router import (
    CrossGatewayArtifactRelayService,
    FleetProfile,
    GatewayNode,
    GatewayPlatform,
    GatewayStatus,
    GatewayTelemetry,
    HostGatewayContextInjector,
    MultiGatewayConnectionPool,
)

from app.schemas.fleet_router import (
    BufferCommandRequest,
    BufferedCommandResponse,
    FleetProfileResponse,
    FleetTopologyResponse,
    FlushResponse,
    GatewayNodeResponse,
    GatewayTelemetryDTO,
    HeartbeatRequest,
    InjectedContextResponse,
    RegisterGatewayRequest,
    RegisterProfileRequest,
    RelayArtifactRequest,
    RelayedArtifactResponse,
)


class FleetRouterService:
    """Singleton service orchestrating multi-machine distributed gateway routing and buffering."""

    _instance: Optional["FleetRouterService"] = None

    def __init__(self) -> None:
        self.connection_pool = MultiGatewayConnectionPool(heartbeat_timeout_seconds=30.0)
        self.context_injector = HostGatewayContextInjector(connection_pool=self.connection_pool)
        self.artifact_relay = CrossGatewayArtifactRelayService(
            connection_pool=self.connection_pool
        )
        self._init_default_local_gateway()

    @classmethod
    def get_instance(cls) -> "FleetRouterService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def _init_default_local_gateway(self) -> None:
        local_node = GatewayNode(
            gateway_id="gw-local-host",
            label="Local Host Gateway",
            host="127.0.0.1",
            port=8080,
            protocol="ws",
            platform=GatewayPlatform.DARWIN,
            status=GatewayStatus.ONLINE,
            latency_ms=0.5,
            telemetry=GatewayTelemetry(
                cpu_pct=10.0,
                mem_pct=35.0,
                active_agents=1,
                queue_depth=0,
            ),
            last_heartbeat=time.time(),
        )
        self.connection_pool.register_gateway(local_node)

        default_profile = FleetProfile(
            profile_id="prof-primary-orchestrator",
            gateway_id="gw-local-host",
            name="Primary Orchestrator",
            avatar="🧭",
            role="Fleet Dispatcher",
            system_context="You are the primary coordinator orchestrating the distributed fleet.",
            is_active=True,
        )
        self.connection_pool.register_profile(default_profile)

    def _to_gateway_response(self, node: GatewayNode) -> GatewayNodeResponse:
        return GatewayNodeResponse(
            gateway_id=node.gateway_id,
            label=node.label,
            host=node.host,
            port=node.port,
            protocol=node.protocol,
            platform=node.platform.value,
            status=node.status.value,
            latency_ms=node.latency_ms,
            telemetry=GatewayTelemetryDTO(
                cpu_pct=node.telemetry.cpu_pct,
                mem_pct=node.telemetry.mem_pct,
                active_agents=node.telemetry.active_agents,
                queue_depth=node.telemetry.queue_depth,
            ),
            last_heartbeat=node.last_heartbeat,
        )

    def _to_profile_response(self, profile: FleetProfile) -> FleetProfileResponse:
        return FleetProfileResponse(
            profile_id=profile.profile_id,
            gateway_id=profile.gateway_id,
            name=profile.name,
            avatar=profile.avatar,
            role=profile.role,
            system_context=profile.system_context,
            is_active=profile.is_active,
        )

    def register_gateway(self, req: RegisterGatewayRequest) -> GatewayNodeResponse:
        platform_enum = GatewayPlatform(req.platform.lower())
        node = GatewayNode(
            gateway_id=req.gateway_id,
            label=req.label,
            host=req.host,
            port=req.port,
            protocol=req.protocol,
            platform=platform_enum,
            status=GatewayStatus.ONLINE,
            latency_ms=req.latency_ms,
            telemetry=GatewayTelemetry(
                cpu_pct=req.cpu_pct,
                mem_pct=req.mem_pct,
                active_agents=req.active_agents,
                queue_depth=req.queue_depth,
            ),
            last_heartbeat=time.time(),
        )
        registered = self.connection_pool.register_gateway(node)
        return self._to_gateway_response(registered)

    def unregister_gateway(self, gateway_id: str) -> None:
        self.connection_pool.unregister_gateway(gateway_id)

    def get_gateway(self, gateway_id: str) -> Optional[GatewayNodeResponse]:
        node = self.connection_pool.get_gateway(gateway_id)
        return self._to_gateway_response(node) if node else None

    def list_gateways(self) -> list[GatewayNodeResponse]:
        nodes = self.connection_pool.list_gateways()
        return [self._to_gateway_response(n) for n in nodes]

    def update_heartbeat(self, gateway_id: str, req: HeartbeatRequest) -> GatewayNodeResponse:
        telemetry = GatewayTelemetry(
            cpu_pct=req.cpu_pct,
            mem_pct=req.mem_pct,
            active_agents=req.active_agents,
            queue_depth=req.queue_depth,
        )
        status_enum = GatewayStatus(req.status.lower()) if req.status else None
        updated = self.connection_pool.update_heartbeat(
            gateway_id=gateway_id,
            telemetry=telemetry,
            latency_ms=req.latency_ms,
            status=status_enum,
        )
        return self._to_gateway_response(updated)

    def register_profile(self, req: RegisterProfileRequest) -> FleetProfileResponse:
        profile = FleetProfile(
            profile_id=req.profile_id,
            gateway_id=req.gateway_id,
            name=req.name,
            avatar=req.avatar,
            role=req.role,
            system_context=req.system_context,
            is_active=req.is_active,
        )
        registered = self.connection_pool.register_profile(profile)
        return self._to_profile_response(registered)

    def get_profile(self, profile_id: str) -> Optional[FleetProfileResponse]:
        p = self.connection_pool.get_profile(profile_id)
        return self._to_profile_response(p) if p else None

    def list_profiles(self) -> list[FleetProfileResponse]:
        profiles = self.connection_pool.list_profiles()
        return [self._to_profile_response(p) for p in profiles]

    def get_injected_context(
        self, profile_id: str, base_context: str = ""
    ) -> InjectedContextResponse:
        profile = self.connection_pool.get_profile(profile_id)
        orig = base_context if base_context else (profile.system_context if profile else "")
        injected = self.context_injector.inject_host_context(profile_id, orig)
        badge = self.context_injector.format_host_badge(profile_id)
        return InjectedContextResponse(
            profile_id=profile_id,
            original_context=orig,
            injected_context=injected,
            host_badge=badge,
        )

    def buffer_command(self, req: BufferCommandRequest) -> BufferedCommandResponse:
        cmd = self.connection_pool.buffer_offline_command(
            gateway_id=req.gateway_id,
            profile_id=req.profile_id,
            command_type=req.command_type,
            payload=req.payload,
        )
        return BufferedCommandResponse(
            command_id=cmd.command_id,
            gateway_id=cmd.gateway_id,
            profile_id=cmd.profile_id,
            command_type=cmd.command_type,
            payload=cmd.payload,
            queued_at=cmd.queued_at,
            retry_count=cmd.retry_count,
        )

    def flush_buffered_commands(self, gateway_id: str) -> FlushResponse:
        flushed = self.connection_pool.flush_buffered_commands(gateway_id)
        return FlushResponse(
            gateway_id=gateway_id,
            flushed_count=len(flushed),
            commands=[
                BufferedCommandResponse(
                    command_id=c.command_id,
                    gateway_id=c.gateway_id,
                    profile_id=c.profile_id,
                    command_type=c.command_type,
                    payload=c.payload,
                    queued_at=c.queued_at,
                    retry_count=c.retry_count,
                )
                for c in flushed
            ],
        )

    def relay_artifact(self, req: RelayArtifactRequest) -> RelayedArtifactResponse:
        envelope = self.artifact_relay.relay_artifact(
            source_gateway=req.source_gateway,
            target_gateway=req.target_gateway,
            name=req.name,
            file_path=req.file_path,
            chunk_data=req.chunk_data,
        )
        is_verified = self.artifact_relay.verify_artifact_integrity(envelope)
        return RelayedArtifactResponse(
            artifact_id=envelope.artifact_id,
            source_gateway=envelope.source_gateway,
            target_gateway=envelope.target_gateway,
            name=envelope.name,
            file_path=envelope.file_path,
            sha256=envelope.sha256,
            chunk_data=envelope.chunk_data,
            created_at=envelope.created_at,
            is_verified=is_verified,
        )

    def get_topology_snapshot(self) -> FleetTopologyResponse:
        gateways = self.list_gateways()
        profiles = self.list_profiles()
        online_count = sum(1 for g in gateways if g.status == "online")
        snap = self.connection_pool.get_topology_snapshot()
        return FleetTopologyResponse(
            gateways=gateways,
            profiles=profiles,
            total_gateways=len(gateways),
            online_gateways=online_count,
            total_buffered_commands=snap.total_buffered_commands,
        )
