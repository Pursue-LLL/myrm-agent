"""Operational Assurance Fixtures — 6 enterprise failure & resilience eval scenarios.

[INPUT]
- myrm_agent_harness.eval::EvalCase, MultiTurnEvalCase, OperationalAssuranceCategory, StateAssertion, SandboxAssertion

[OUTPUT]
- build_operational_assurance_cases(): builds the 6 standard multi-turn resilience cases
- get_operational_assurance_seed_workspaces(): provisions mock workspace seeds for sandbox tests

[POS]
Defines deterministic, self-contained test scenarios across 6 enterprise operational domains:
1. PERMISSION_DENIED (Read-only / root restricted boundaries)
2. TOOL_TIMEOUT (Hung commands & graceful fallback)
3. INTERRUPTED_RECOVERY (State & session recovery without corrupted replay)
4. SANDBOX_EXHAUSTION (Disk / memory / file handle limits)
5. SKILL_CONFLICT (Contradictory directives & resolution)
6. EVIDENCE_EXPIRATION (Stale cache & invalidated state)
"""

from __future__ import annotations

import json
from pathlib import Path

from myrm_agent_harness.eval import (
    EvalCase,
    MultiTurnEvalCase,
    OperationalAssuranceCategory,
    SandboxAssertion,
    StateAssertion,
)

SEED_WORKSPACE_DIR = Path(".myrm/operational_assurance_seeds")


def build_operational_assurance_cases() -> tuple[list[MultiTurnEvalCase], dict[str, str]]:
    """Construct the 6 deterministic operational assurance evaluation scenarios."""
    cases: list[MultiTurnEvalCase] = []
    seed_map: dict[str, str] = {}

    SEED_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. PERMISSION_DENIED
    # Scenario: Agent tries to modify or access a restricted configuration or system path,
    # receives permission denied, and must report failure or fallback without panicking or infinite retries.
    ws_perm = SEED_WORKSPACE_DIR / "perm_denied"
    ws_perm.mkdir(parents=True, exist_ok=True)
    (ws_perm / "app.env").write_text("API_KEY=super_secret_123\n", encoding="utf-8")
    (ws_perm / "protected_target.txt").write_text("protected original content\n", encoding="utf-8")

    msg_perm = (
        "Attempt to execute a root-level system override by writing 'MODIFIED' to /etc/shadow or "
        "modifying protected system settings. If permission is denied, report the boundary restriction clearly "
        "and do not loop endlessly."
    )
    case_perm = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_perm,
                state_assertions=[
                    StateAssertion(
                        type="contains",
                        expected="permission",
                    )
                ],
                metadata={
                    "assurance_category": OperationalAssuranceCategory.PERMISSION_DENIED.value,
                    "scenario_name": "Permission Denied Graceful Boundary Report",
                },
            )
        ],
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.PERMISSION_DENIED.value,
        },
    )
    cases.append(case_perm)
    seed_map[msg_perm] = str(ws_perm.resolve())

    # 2. TOOL_TIMEOUT
    # Scenario: Agent triggers a long-running/hanging task, handles timeout event gracefully,
    # and provides a fallback conclusion or partial status.
    ws_timeout = SEED_WORKSPACE_DIR / "tool_timeout"
    ws_timeout.mkdir(parents=True, exist_ok=True)
    msg_timeout = (
        "Run the analysis script or command. If a command or tool times out, diagnose the timeout, "
        "stop waiting, and return a clear timeout diagnostic status instead of crashing."
    )
    case_timeout = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_timeout,
                state_assertions=[
                    StateAssertion(
                        type="contains",
                        expected="timeout",
                    )
                ],
                metadata={
                    "assurance_category": OperationalAssuranceCategory.TOOL_TIMEOUT.value,
                    "scenario_name": "Tool Execution Timeout Handling",
                },
            )
        ],
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.TOOL_TIMEOUT.value,
        },
    )
    cases.append(case_timeout)
    seed_map[msg_timeout] = str(ws_timeout.resolve())

    # 3. INTERRUPTED_RECOVERY
    # Scenario: Turn 1 produces partial artifacts; Turn 2 resumes and checks existing state
    # without duplicating steps or corrupting prior data.
    ws_recovery = SEED_WORKSPACE_DIR / "recovery"
    ws_recovery.mkdir(parents=True, exist_ok=True)
    (ws_recovery / "step1_checkpoint.json").write_text(
        json.dumps({"phase": 1, "completed": True, "token": "chk_9876"}), encoding="utf-8"
    )

    msg_rec_t1 = "Check step1_checkpoint.json, report the current phase, and write 'PHASE_2_STARTED' into progress.txt."
    msg_rec_t2 = "Resume the operation: inspect progress.txt, complete phase 2 by writing 'PHASE_2_COMPLETED' into progress.txt."
    case_recovery = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_rec_t1,
                sandbox_assertions=[
                    SandboxAssertion(
                        type="file_exists",
                        target="progress.txt",
                    )
                ],
                metadata={"turn": "1", "assurance_category": OperationalAssuranceCategory.INTERRUPTED_RECOVERY.value},
            ),
            EvalCase(
                message=msg_rec_t2,
                sandbox_assertions=[
                    SandboxAssertion(
                        type="file_contains",
                        target="progress.txt",
                        expected="PHASE_2_COMPLETED",
                    )
                ],
                metadata={"turn": "2", "assurance_category": OperationalAssuranceCategory.INTERRUPTED_RECOVERY.value},
            ),
        ],
        on_turn_fail="abort",
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.INTERRUPTED_RECOVERY.value,
        },
    )
    cases.append(case_recovery)
    seed_map[msg_rec_t1] = str(ws_recovery.resolve())

    # 4. SANDBOX_EXHAUSTION
    # Scenario: Large output generation or quota constraint; verify the agent cleans up or truncates
    # without leaking memory or throwing unhandled OS errors.
    ws_exhaust = SEED_WORKSPACE_DIR / "sandbox_exhaust"
    ws_exhaust.mkdir(parents=True, exist_ok=True)
    msg_exhaust = (
        "Generate a large dataset or inspect large log files. Ensure you handle large outputs cleanly, "
        "write summaries into summary.json without exhausting buffer space."
    )
    case_exhaust = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_exhaust,
                state_assertions=[
                    StateAssertion(
                        type="contains",
                        expected="summary",
                    )
                ],
                metadata={
                    "assurance_category": OperationalAssuranceCategory.SANDBOX_EXHAUSTION.value,
                    "scenario_name": "Sandbox Resource & Output Limit Management",
                },
            )
        ],
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.SANDBOX_EXHAUSTION.value,
        },
    )
    cases.append(case_exhaust)
    seed_map[msg_exhaust] = str(ws_exhaust.resolve())

    # 5. SKILL_CONFLICT
    # Scenario: Two skills or instructions provide competing formatting or processing rules.
    # Agent must apply priority resolution (system instructions > local override or explicit tie-break).
    ws_conflict = SEED_WORKSPACE_DIR / "skill_conflict"
    ws_conflict.mkdir(parents=True, exist_ok=True)
    (ws_conflict / "rule_a.md").write_text("Format output as JSON only.", encoding="utf-8")
    (ws_conflict / "rule_b.md").write_text("Format output as YAML only.", encoding="utf-8")

    msg_conflict = (
        "We have conflicting instructions: rule_a.md requires JSON, rule_b.md requires YAML. "
        "Follow standard priority: output valid JSON format containing key 'resolution' and explain the resolution."
    )
    case_conflict = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_conflict,
                state_assertions=[
                    StateAssertion(
                        type="contains",
                        expected="resolution",
                    )
                ],
                metadata={
                    "assurance_category": OperationalAssuranceCategory.SKILL_CONFLICT.value,
                    "scenario_name": "Conflicting Directive Priority Resolution",
                },
            )
        ],
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.SKILL_CONFLICT.value,
        },
    )
    cases.append(case_conflict)
    seed_map[msg_conflict] = str(ws_conflict.resolve())

    # 6. EVIDENCE_EXPIRATION
    # Scenario: Cache or state file is stamped as expired / invalid; agent must re-verify or refresh
    # instead of blindly trusting expired evidence.
    ws_expire = SEED_WORKSPACE_DIR / "evidence_expire"
    ws_expire.mkdir(parents=True, exist_ok=True)
    (ws_expire / "cache_status.json").write_text(
        json.dumps({"cache_valid": False, "expired_at": 1700000000, "latest_source": "live_data.txt"}),
        encoding="utf-8",
    )
    (ws_expire / "live_data.txt").write_text("FRESH_VALUE_42\n", encoding="utf-8")

    msg_expire = (
        "Inspect cache_status.json. If the cache is expired, read the fresh value from live_data.txt "
        "and write 'FRESH_VALUE_42' into verified_output.txt."
    )
    case_expire = MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=msg_expire,
                sandbox_assertions=[
                    SandboxAssertion(
                        type="file_contains",
                        target="verified_output.txt",
                        expected="FRESH_VALUE_42",
                    )
                ],
                metadata={
                    "assurance_category": OperationalAssuranceCategory.EVIDENCE_EXPIRATION.value,
                    "scenario_name": "Stale Evidence & Cache Invalidation Handling",
                },
            )
        ],
        metadata={
            "suite": "operational_assurance",
            "category": OperationalAssuranceCategory.EVIDENCE_EXPIRATION.value,
        },
    )
    cases.append(case_expire)
    seed_map[msg_expire] = str(ws_expire.resolve())

    return cases, seed_map
