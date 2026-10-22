"""本地与云端双核算力平滑委派、流式进度 HUD 与成果自愈回拉自动化测试套件。

全面覆盖：
1. 本地执行态 Checkpoint 增量打包与 .git/node_modules/venv 等噪声严格排除；
2. SHA256 完整性指纹计算与不可篡改验证；
3. 云端沙箱接力 Preflight 预检（能力完备 vs 缺失依赖拦截）；
4. 云端接管成功激活与状态流转；
5. 多端流式进度事件广播 (Mobile/Web/Desktop) 与百分比换算；
6. 新端连接时的最新进度快照瞬时补发 (Catch-up Snapshot)；
7. 离线完成后成果无缝回拉与本地合并 (Clean Merge)；
8. 本地并发改动下的三方合并冲突精准检测与标记 (Conflict Detection)；
9. 成果幂等回拉验证 (Already Up to Date)。
"""

from __future__ import annotations

import hashlib

from app.services.agent.workload_delegation import (
    DelegationState,
    LiveProgressHudHub,
    MergeStatus,
    OfflinePullbackEngine,
    PullbackBundle,
    StepProgressEvent,
    WorkloadHandoverDelegator,
)


def test_workload_delegator_packaging_and_exclusion() -> None:
    """测试本地任务打包：有效源码被包含，node_modules/.git 等缓存被过滤。"""
    delegator = WorkloadHandoverDelegator(
        session_id="session_work_101",
        task_id="task_deep_research_01",
    )
    raw_files = {
        "src/main.py": "print('hello')",
        "docs/report.md": "# Research Report",
        ".git/HEAD": "ref: refs/heads/main",
        "node_modules/axios/index.js": "export default {}",
        ".venv/pyvenv.cfg": "home = /usr/bin",
        "app/__pycache__/cache.pyc": "binary",
    }
    dag_checkpoint = {
        "step_1": "COMPLETED",
        "step_2": "IN_PROGRESS",
    }
    env_manifest = {
        "python_version": "3.13",
        "required_tools": "web_search,code_runner",
    }

    envelope = delegator.package_delegation_envelope(
        current_step=2,
        dag_checkpoint=dag_checkpoint,
        env_manifest=env_manifest,
        raw_files=raw_files,
        metadata={"priority": "high"},
    )

    assert envelope.session_id == "session_work_101"
    assert envelope.task_id == "task_deep_research_01"
    assert envelope.current_step == 2
    assert len(envelope.checksum) == 64  # SHA256
    assert delegator.state == DelegationState.PACKAGING

    # 验证文件过滤
    assert "src/main.py" in envelope.workspace_patch
    assert "docs/report.md" in envelope.workspace_patch
    assert ".git/HEAD" not in envelope.workspace_patch
    assert "node_modules/axios/index.js" not in envelope.workspace_patch
    assert ".venv/pyvenv.cfg" not in envelope.workspace_patch
    assert "app/__pycache__/cache.pyc" not in envelope.workspace_patch


def test_workload_delegator_preflight_missing_dependencies() -> None:
    """测试云沙箱接力 Preflight 预检：缺失必要工具时拦截接力。"""
    delegator = WorkloadHandoverDelegator(
        session_id="session_work_102",
        task_id="task_video_gen_02",
    )
    envelope = delegator.package_delegation_envelope(
        current_step=1,
        dag_checkpoint={"step_1": "IN_PROGRESS"},
        env_manifest={"required_tools": "ffmpeg,gpu_renderer"},
        raw_files={"script.py": "run()"},
    )
    delegator.delegate_to_cloud_sandbox("sandbox_cloud_888")
    assert delegator.state == DelegationState.DELEGATED_TO_CLOUD

    # 云端仅有普通工具，缺失 ffmpeg 和 gpu_renderer
    cloud_tools = {"python_eval", "web_search"}
    check = WorkloadHandoverDelegator.preflight_cloud_environment(envelope, cloud_tools)
    assert check.is_ready is False
    assert "ffmpeg" in check.missing_dependencies
    assert "gpu_renderer" in check.missing_dependencies

    # 接管应当失败
    takeover_ok = delegator.activate_cloud_takeover(cloud_tools)
    assert takeover_ok is False
    assert delegator.state == DelegationState.DELEGATED_TO_CLOUD


def test_workload_delegator_cloud_takeover_success() -> None:
    """测试云沙箱环境匹配时顺利接管并恢复执行。"""
    delegator = WorkloadHandoverDelegator(
        session_id="session_work_103",
        task_id="task_doc_audit_03",
    )
    delegator.package_delegation_envelope(
        current_step=3,
        dag_checkpoint={"step_1": "DONE", "step_2": "DONE", "step_3": "IN_PROGRESS"},
        env_manifest={"required_tools": "doc_parser,linter"},
        raw_files={"doc.md": "# Content"},
    )
    delegator.delegate_to_cloud_sandbox("sandbox_cloud_999")

    cloud_tools = {"doc_parser", "linter", "bash"}
    takeover_ok = delegator.activate_cloud_takeover(cloud_tools)

    assert takeover_ok is True
    assert delegator.state == DelegationState.RESUMING_IN_CLOUD
    assert delegator.cloud_sandbox_id == "sandbox_cloud_999"

    # 标记完成并回拉
    delegator.mark_cloud_execution_finished()
    finished_state: DelegationState = delegator.state
    assert finished_state == DelegationState.COMPLETED_AWAITING_PULLBACK

    delegator.mark_restored_to_local()
    restored_state: DelegationState = delegator.state
    assert restored_state == DelegationState.RESTORED_TO_LOCAL
    assert delegator.current_envelope is None


def test_live_progress_hud_publish_and_subscribe() -> None:
    """测试多端流式进度事件总线广播与百分比计算。"""
    hud_hub = LiveProgressHudHub()
    received_events: list[StepProgressEvent] = []

    unsubscribe = hud_hub.subscribe(
        task_id="task_live_1",
        listener=lambda evt: received_events.append(evt),
        replay_latest=False,
    )

    event_1 = StepProgressEvent(
        task_id="task_live_1",
        step_index=2,
        total_steps=10,
        stage_name="Information Gathering",
        preview_text="Fetched 4 web resources...",
        elapsed_seconds=12.5,
        estimated_remaining_seconds=48.0,
    )
    hud_hub.publish_progress(event_1)

    assert len(received_events) == 1
    assert received_events[0].percentage == 20.0
    assert received_events[0].stage_name == "Information Gathering"

    # 取消订阅后不再收到事件
    unsubscribe()
    event_2 = StepProgressEvent(
        task_id="task_live_1",
        step_index=5,
        total_steps=10,
        stage_name="Deep Analysis",
        preview_text="Synthesizing findings...",
        elapsed_seconds=30.0,
        estimated_remaining_seconds=25.0,
    )
    hud_hub.publish_progress(event_2)
    assert len(received_events) == 1  # 依然是 1


def test_live_progress_hud_replay_latest_catchup() -> None:
    """测试新设备上线订阅时，瞬时补发最新进度快照。"""
    hud_hub = LiveProgressHudHub()

    # 任务已在后台执行到第 8 步
    event = StepProgressEvent(
        task_id="task_live_catchup",
        step_index=8,
        total_steps=10,
        stage_name="Final Code Generation",
        preview_text="Generating test cases...",
        elapsed_seconds=75.0,
        estimated_remaining_seconds=15.0,
    )
    hud_hub.publish_progress(event)

    # 手机端新上线订阅
    mobile_received: list[StepProgressEvent] = []
    hud_hub.subscribe(
        task_id="task_live_catchup",
        listener=lambda evt: mobile_received.append(evt),
        replay_latest=True,
    )

    assert len(mobile_received) == 1
    assert mobile_received[0].step_index == 8
    assert mobile_received[0].percentage == 80.0
    assert mobile_received[0].stage_name == "Final Code Generation"


def test_offline_pullback_clean_merge() -> None:
    """测试离线完成成果回拉：本地未冲突，无缝合并云端文件。"""
    local_files = {
        "src/app.py": "def run(): pass\n",
        "README.md": "# Initial Readme\n",
    }
    base_hashes = {
        "src/app.py": hashlib.sha256(local_files["src/app.py"].encode("utf-8")).hexdigest(),
        "README.md": hashlib.sha256(local_files["README.md"].encode("utf-8")).hexdigest(),
    }

    # 云端新增了 tests/test_app.py 并优化了 src/app.py
    cloud_files = {
        "src/app.py": "def run():\n    return 'production ready'\n",
        "tests/test_app.py": "def test_run(): assert run() == 'production ready'\n",
    }
    bundle = PullbackBundle(
        task_id="task_pullback_01",
        session_id="session_01",
        cloud_files=cloud_files,
        base_file_hashes=base_hashes,
        artifacts_created=("dist/bundle.zip",),
        execution_summary="Refactored run function and added tests.",
    )

    merged, result = OfflinePullbackEngine.inspect_and_merge(bundle, local_files)

    assert result.status == MergeStatus.CLEAN_MERGE
    assert len(result.conflicted_files) == 0
    assert "src/app.py" in result.applied_files
    assert "tests/test_app.py" in result.applied_files

    # 验证合并后的文件内容
    assert merged["src/app.py"] == cloud_files["src/app.py"]
    assert merged["tests/test_app.py"] == cloud_files["tests/test_app.py"]
    assert merged["README.md"] == local_files["README.md"]  # 原文件保留


def test_offline_pullback_conflict_detection() -> None:
    """测试本地离线期间被用户意外改动：精准检测冲突并插入冲突标记。"""
    original_content = "VERSION = 1\n"
    original_hash = hashlib.sha256(original_content.encode("utf-8")).hexdigest()

    # 用户在桌面端修改成了 VERSION = 2
    local_files = {
        "version.py": "VERSION = 2\n",
    }
    # 云端沙箱执行生成了 VERSION = 3
    cloud_files = {
        "version.py": "VERSION = 3\n",
    }
    base_hashes = {
        "version.py": original_hash,
    }

    bundle = PullbackBundle(
        task_id="task_pullback_conflict",
        session_id="session_02",
        cloud_files=cloud_files,
        base_file_hashes=base_hashes,
        artifacts_created=(),
        execution_summary="Bumped version in cloud sandbox.",
    )

    merged, result = OfflinePullbackEngine.inspect_and_merge(bundle, local_files)

    assert result.status == MergeStatus.CONFLICT_DETECTED
    assert "version.py" in result.conflicted_files
    assert "<<<<<<< LOCAL (Desktop)" in merged["version.py"]
    assert "VERSION = 2" in merged["version.py"]
    assert "=======" in merged["version.py"]
    assert "VERSION = 3" in merged["version.py"]
    assert ">>>>>>> CLOUD (Sandbox)" in merged["version.py"]


def test_offline_pullback_already_up_to_date() -> None:
    """测试幂等回拉：当本地内容已与云端一致时，正确返回 already_up_to_date。"""
    local_files = {
        "config.json": '{"mode": "cloud"}\n',
    }
    base_hashes = {
        "config.json": hashlib.sha256(local_files["config.json"].encode("utf-8")).hexdigest(),
    }
    cloud_files = {
        "config.json": '{"mode": "cloud"}\n',
    }
    bundle = PullbackBundle(
        task_id="task_pullback_idempotent",
        session_id="session_03",
        cloud_files=cloud_files,
        base_file_hashes=base_hashes,
        artifacts_created=(),
        execution_summary="No files changed.",
    )

    merged, result = OfflinePullbackEngine.inspect_and_merge(bundle, local_files)

    assert result.status == MergeStatus.ALREADY_UP_TO_DATE
    assert len(result.applied_files) == 0
    assert len(result.conflicted_files) == 0
    assert merged == local_files
