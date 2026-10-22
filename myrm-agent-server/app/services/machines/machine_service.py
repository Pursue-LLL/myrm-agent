"""[INPUT] MachineNode, MachineMetrics, and TakeoverSession models.
[OUTPUT] MachineService managing self-hosted machine fleet, heartbeats, and live takeover states.
[POS] app/services/machines/machine_service.py.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import uuid

from .machine_types import (
    MachineMetrics,
    MachineNode,
    MachinePlatform,
    MachineStatus,
    RegistrationTokenResponse,
    TakeoverSession,
    TakeoverState,
)


class MachineService:
    """Service managing self-hosted machine fleet registry and live takeover sessions."""

    _instance: Optional["MachineService"] = None

    def __init__(self) -> None:
        self._machines: Dict[str, MachineNode] = {}
        self._takeovers: Dict[str, TakeoverSession] = {}
        self._seed_default_machines()

    @classmethod
    def get_instance(cls) -> "MachineService":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset instance for isolated unit tests."""
        cls._instance = None

    def _seed_default_machines(self) -> None:
        """Seed initial cluster nodes for immediate zero-config dashboard visualization."""
        now_iso = datetime.now(timezone.utc).isoformat()

        mac_node = MachineNode(
            machine_id="mach-mac-studio-01",
            hostname="MacStudio-M2-Ultra.local",
            display_name="Mac Studio M2 Ultra (主节点)",
            platform=MachinePlatform.DARWIN,
            ip_address="192.168.1.108",
            status=MachineStatus.ONLINE,
            metrics=MachineMetrics(
                cpu_usage_pct=28.4,
                memory_usage_pct=42.1,
                disk_usage_pct=34.8,
                active_tasks_count=2,
                last_heartbeat_at=now_iso,
            ),
            registered_at=now_iso,
            tags=["Apple Silicon", "128GB Unified", "Metal 3", "Local LLM"],
            screen_stream_url="webrtc://192.168.1.108:8554/live/desktop",
        )

        linux_node = MachineNode(
            machine_id="mach-gpu-worker-02",
            hostname="ubuntu-h100-cloud-01",
            display_name="Cloud GPU Worker 02 (云端高算力)",
            platform=MachinePlatform.LINUX,
            ip_address="10.0.4.15",
            status=MachineStatus.BUSY,
            metrics=MachineMetrics(
                cpu_usage_pct=76.2,
                memory_usage_pct=68.5,
                disk_usage_pct=52.0,
                active_tasks_count=5,
                last_heartbeat_at=now_iso,
            ),
            registered_at=now_iso,
            tags=["NVIDIA H100", "CUDA 12.4", "vLLM", "Headless"],
            screen_stream_url="webrtc://10.0.4.15:8554/live/display",
        )

        self._machines[mac_node.machine_id] = mac_node
        self._machines[linux_node.machine_id] = linux_node

    def list_machines(self) -> List[MachineNode]:
        """List all registered worker machines in the fleet."""
        return list(self._machines.values())

    def get_machine(self, machine_id: str) -> Optional[MachineNode]:
        """Get a single machine by ID."""
        return self._machines.get(machine_id)

    def generate_registration_token(self, platform: MachinePlatform = MachinePlatform.DARWIN) -> RegistrationTokenResponse:
        """Generate a single-line shell registration command for 1-click node onboarding."""
        token = f"tok-{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=2)).isoformat()

        if platform == MachinePlatform.WINDOWS:
            cmd = (
                f'powershell -ExecutionPolicy Bypass -Command "'
                f"Invoke-WebRequest -Uri https://get.myrm.ai/connect.ps1 -OutFile connect.ps1; "
                f'.\\connect.ps1 -Token {token}"'
            )
        else:
            cmd = f"curl -fsSL https://get.myrm.ai/connect.sh | bash -s -- --token {token}"

        return RegistrationTokenResponse(
            token=token,
            platform=platform,
            quick_command=cmd,
            expires_at=expires_at,
        )

    def register_machine(self, node: MachineNode) -> MachineNode:
        """Register or update a machine node."""
        self._machines[node.machine_id] = node
        return node

    def heartbeat(self, machine_id: str, metrics: MachineMetrics) -> MachineNode:
        """Update machine metrics and refresh heartbeat."""
        node = self._machines.get(machine_id)
        if not node:
            now_iso = datetime.now(timezone.utc).isoformat()
            node = MachineNode(
                machine_id=machine_id,
                hostname=f"node-{machine_id[:8]}",
                display_name=f"Self-Hosted Node ({machine_id[:8]})",
                platform=MachinePlatform.LINUX,
                ip_address="127.0.0.1",
                status=MachineStatus.ONLINE,
                metrics=metrics,
                registered_at=now_iso,
                tags=["Self-Hosted"],
            )
            self._machines[machine_id] = node
        else:
            node.metrics = metrics
            # If not in human takeover, status reflects activity
            if node.status != MachineStatus.TAKEOVER:
                node.status = MachineStatus.BUSY if metrics.active_tasks_count > 0 else MachineStatus.ONLINE

        return node

    def initiate_takeover(self, machine_id: str, operator_id: str = "user-primary") -> TakeoverSession:
        """Seize human interactive control over the remote machine screen."""
        node = self._machines.get(machine_id)
        if node:
            node.status = MachineStatus.TAKEOVER

        now_iso = datetime.now(timezone.utc).isoformat()
        session_id = f"takeover-{uuid.uuid4().hex[:12]}"
        session = TakeoverSession(
            session_id=session_id,
            machine_id=machine_id,
            state=TakeoverState.HUMAN_TAKEOVER,
            operator_id=operator_id,
            started_at=now_iso,
            updated_at=now_iso,
        )
        self._takeovers[machine_id] = session
        return session

    def release_takeover(self, machine_id: str) -> TakeoverSession:
        """Release human control and hand execution back to the autonomous agent."""
        node = self._machines.get(machine_id)
        if node:
            node.status = MachineStatus.ONLINE

        now_iso = datetime.now(timezone.utc).isoformat()
        session = self._takeovers.get(machine_id)
        if session:
            session.state = TakeoverState.AGENT
            session.operator_id = None
            session.updated_at = now_iso
        else:
            session = TakeoverSession(
                session_id=f"takeover-{uuid.uuid4().hex[:12]}",
                machine_id=machine_id,
                state=TakeoverState.AGENT,
                operator_id=None,
                started_at=now_iso,
                updated_at=now_iso,
            )
            self._takeovers[machine_id] = session

        return session

    def get_takeover_session(self, machine_id: str) -> Optional[TakeoverSession]:
        """Fetch current takeover session for a machine."""
        return self._takeovers.get(machine_id)
