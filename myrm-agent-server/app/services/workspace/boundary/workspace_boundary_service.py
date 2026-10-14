"""[INPUT]
ProjectSwitchHandshakeRequest, ThreeCurrentsBoundary, MultiRepoWorktreeEntry from app.services.workspace.boundary.boundary_types
[OUTPUT]
WorkspaceBoundaryInspectorService for probing host environment, Git worktrees, and project switch handshakes.
[POS]
app/services/workspace/boundary/workspace_boundary_service.py
"""

import hashlib
import hmac
import os
import platform
import subprocess
import time
from typing import Optional

from app.services.workspace.boundary.boundary_types import (
    ExecutionHostType,
    MultiRepoWorktreeEntry,
    ProjectSwitchHandshakeRequest,
    ProjectSwitchHandshakeResponse,
    RiskLevel,
    ThreeCurrentsBoundary,
)

_SECRET_SALT = b"myrm-workspace-boundary-handshake-salt-2026"


class WorkspaceBoundaryInspectorService:
    """Service inspecting 3-currents execution boundary and verifying project switch handshakes."""

    def __init__(self, default_cwd: Optional[str] = None) -> None:
        self._default_cwd = default_cwd or os.getcwd()

    def detect_host_execution_topology(self) -> tuple[ExecutionHostType, str, str]:
        """Detect execution host topology: local host, cloud sandbox, or docker container."""
        sandbox_id = os.environ.get("SANDBOX_ID") or os.environ.get("MYRM_SANDBOX_ID")
        if sandbox_id or os.environ.get("MYRM_CLOUD_SANDBOX") == "1":
            label = f"☁️ Cloud Sandbox #{sandbox_id or 'default'}"
            return "cloud_sandbox", label, sandbox_id or "cloud-sbx"

        if os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "1":
            return "docker_container", "🐳 Docker Container", "docker-local"

        sys_name = platform.system()
        if sys_name == "Darwin":
            display = "💻 Local Mac"
        elif sys_name == "Linux":
            display = "🐧 Local Linux"
        elif sys_name == "Windows":
            display = "🪟 Local Windows"
        else:
            display = f"🖥️ Local Host ({sys_name})"

        node_id = platform.node() or "localhost"
        return "local_host", display, f"host-{node_id}"

    def inspect_git_state(self, target_dir: str) -> tuple[bool, str, Optional[str], int]:
        """Safely inspect Git repository status with read-only commands and strict timeout.

        Returns: (is_git_repo, branch_name, worktree_name, uncommitted_changes_count)
        """
        if not os.path.isdir(target_dir):
            return False, "", None, 0

        try:
            # Check inside work tree
            check_proc = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if check_proc.returncode != 0 or check_proc.stdout.strip() != "true":
                return False, "", None, 0

            # Get current branch
            branch_proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""

            # Check uncommitted changes count
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            dirty_count = 0
            if status_proc.returncode == 0 and status_proc.stdout.strip():
                dirty_count = len([line for line in status_proc.stdout.splitlines() if line.strip()])

            # Detect worktree name if directory is not main git repo root
            toplevel_proc = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            worktree_label: Optional[str] = None
            if toplevel_proc.returncode == 0:
                toplevel = toplevel_proc.stdout.strip()
                basename = os.path.basename(toplevel)
                if basename:
                    worktree_label = basename

            return True, branch, worktree_label, dirty_count
        except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
            return False, "", None, 0

    def inspect_three_currents(
        self,
        session_id: str = "default-session",
        project_id: str = "default-project",
        project_name: Optional[str] = None,
        session_goal: Optional[str] = None,
        custom_cwd: Optional[str] = None,
    ) -> ThreeCurrentsBoundary:
        """Inspect and return the three currents execution boundary."""
        cwd = custom_cwd or self._default_cwd
        resolved_cwd = os.path.abspath(cwd)
        host_type, host_label, host_id = self.detect_host_execution_topology()
        is_git, branch, worktree, dirty_count = self.inspect_git_state(resolved_cwd)

        repo_name = os.path.basename(resolved_cwd) if resolved_cwd else "workspace"
        p_name = project_name or repo_name
        goal = session_goal or "Maintain and iterate codebase tasks"

        return ThreeCurrentsBoundary(
            session_id=session_id,
            project_id=project_id,
            project_name=p_name,
            session_goal=goal,
            cwd=resolved_cwd,
            repo_name=repo_name,
            git_branch=branch or "detached",
            git_worktree=worktree,
            git_is_clean=(dirty_count == 0),
            git_uncommitted_changes=dirty_count,
            execution_host_type=host_type,
            execution_host_label=host_label,
            execution_host_id=host_id,
            inspected_at=time.time(),
        )

    def handshake_project_switch(
        self,
        request: ProjectSwitchHandshakeRequest,
    ) -> ProjectSwitchHandshakeResponse:
        """Execute read-only environment probe to evaluate safety of switching workspace project."""
        target_path = os.path.abspath(request.target_path)
        warnings: list[str] = []

        if not os.path.exists(target_path):
            return ProjectSwitchHandshakeResponse(
                target_project_id=request.target_project_id,
                target_path=target_path,
                path_exists=False,
                is_git_repo=False,
                git_branch="",
                git_worktree=None,
                git_uncommitted_changes=0,
                risk_level="blocked",
                warnings=[f"Target workspace path '{target_path}' does not exist on disk."],
                can_switch=False,
                handshake_token="",
            )

        if not os.path.isdir(target_path):
            return ProjectSwitchHandshakeResponse(
                target_project_id=request.target_project_id,
                target_path=target_path,
                path_exists=True,
                is_git_repo=False,
                git_branch="",
                git_worktree=None,
                git_uncommitted_changes=0,
                risk_level="blocked",
                warnings=[f"Target workspace path '{target_path}' is a file, not a directory."],
                can_switch=False,
                handshake_token="",
            )

        is_git, branch, worktree, dirty_count = self.inspect_git_state(target_path)
        risk: RiskLevel = "safe"

        if not is_git:
            warnings.append("Target directory is not a Git repository. Version tracking disabled.")
            risk = "warning"
        elif dirty_count > 0:
            warnings.append(
                f"Target workspace has {dirty_count} uncommitted changes. Beware of uncommitted edits."
            )
            risk = "warning"

        token = self._generate_handshake_token(request.target_project_id, target_path)

        return ProjectSwitchHandshakeResponse(
            target_project_id=request.target_project_id,
            target_path=target_path,
            path_exists=True,
            is_git_repo=is_git,
            git_branch=branch,
            git_worktree=worktree,
            git_uncommitted_changes=dirty_count,
            risk_level=risk,
            warnings=warnings,
            can_switch=True,
            handshake_token=token,
        )

    def list_worktrees(self, target_dir: Optional[str] = None) -> list[MultiRepoWorktreeEntry]:
        """List active repositories and worktrees associated with target workspace directory."""
        dir_to_inspect = os.path.abspath(target_dir or self._default_cwd)
        if not os.path.isdir(dir_to_inspect):
            return []

        entries: list[MultiRepoWorktreeEntry] = []
        try:
            proc = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=dir_to_inspect,
                capture_output=True,
                text=True,
                timeout=2.5,
                check=False,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                # Fallback: check if single repo
                is_git, branch, _, _ = self.inspect_git_state(dir_to_inspect)
                if is_git:
                    entries.append(
                        MultiRepoWorktreeEntry(
                            repo=os.path.basename(dir_to_inspect),
                            worktree=None,
                            branch=branch or "HEAD",
                            path=dir_to_inspect,
                            is_active=True,
                        )
                    )
                return entries

            current_path = ""
            current_branch = ""
            current_head = ""

            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("worktree "):
                    current_path = line[len("worktree ") :].strip()
                elif line.startswith("branch "):
                    ref = line[len("branch ") :].strip()
                    current_branch = ref.split("/")[-1] if "/" in ref else ref
                elif line.startswith("HEAD "):
                    current_head = line[len("HEAD ") :].strip()
                elif not line and current_path:
                    # End of one worktree entry block
                    repo_name = os.path.basename(current_path)
                    entries.append(
                        MultiRepoWorktreeEntry(
                            repo=repo_name,
                            worktree=repo_name if current_path != dir_to_inspect else None,
                            branch=current_branch or current_head[:7] or "detached",
                            path=current_path,
                            is_active=(current_path == dir_to_inspect),
                        )
                    )
                    current_path = ""
                    current_branch = ""
                    current_head = ""

            if current_path:
                repo_name = os.path.basename(current_path)
                entries.append(
                    MultiRepoWorktreeEntry(
                        repo=repo_name,
                        worktree=repo_name if current_path != dir_to_inspect else None,
                        branch=current_branch or current_head[:7] or "detached",
                        path=current_path,
                        is_active=(current_path == dir_to_inspect),
                    )
                )

        except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
            pass

        return entries

    def _generate_handshake_token(self, project_id: str, path: str) -> str:
        """Create a verifiable HMAC token for the handshake response."""
        data = f"{project_id}:{path}:{int(time.time() // 60)}".encode()
        return hmac.new(_SECRET_SALT, data, hashlib.sha256).hexdigest()
