"""用户数据与智能体资产全量一键快照备份、差异增量导出与跨机灾难恢复自动化测试套件。

全面覆盖：
1. 全资产一致性快照导出与 SHA256 签名校验；
2. 敏感凭据脱敏（API Key / Token / Secret 自动递归替换为 ***REDACTED***）；
3. 关闭脱敏时的原始凭据完整保留；
4. 差异增量备份计算（只保留新增与修改实体，过滤未改动实体，体积缩减）；
5. 灾难恢复 Preflight 校验通过；
6. 存档包防篡改校验（篡改后被 Preflight 精准拒绝）；
7. 跨主版本不兼容拦截；
8. Dry-run 演练模式（只做评估不污染目标存储）；
9. 真实灾难恢复原子回填与全量实体恢复。
"""

from __future__ import annotations

import json
from typing import MutableMapping

from app.services.backup import (
    REDACTED_PLACEHOLDER,
    BackupArchiveBundle,
    BackupManifest,
    DisasterRecoveryWizard,
    FullStackSnapshotExporter,
    IncrementalBackupEngine,
)


def test_full_stack_exporter_creates_valid_bundle_and_checksum() -> None:
    """测试全量一致性快照导出：生成完整的 manifest、文件指纹与全局 checksum。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")

    db_tables = {
        "users": json.dumps([{"id": "u1", "name": "Alice"}]),
        "settings": json.dumps({"theme": "dark"}),
    }
    agent_profiles = {
        "researcher": json.dumps({"role": "Deep Researcher", "model": "deepseek-r1"}),
    }
    custom_skills = {
        "web_scraper/run.py": "def scrape(): pass",
    }
    cron_schedules = {
        "daily_report": json.dumps({"schedule": "0 9 * * *", "action": "summarize"}),
    }
    memory_records = {
        "mem_01": "User prefers concise answers",
    }

    bundle = exporter.export_snapshot(
        backup_id="bak_full_001",
        database_tables=db_tables,
        agent_profiles=agent_profiles,
        custom_skills=custom_skills,
        cron_schedules=cron_schedules,
        memory_records=memory_records,
        scrub_credentials=True,
    )

    manifest = bundle.manifest
    assert manifest.backup_id == "bak_full_001"
    assert manifest.app_version == "0.21.0"
    assert manifest.is_incremental is False
    assert manifest.base_backup_id is None
    assert len(manifest.checksum) == 64
    assert len(manifest.file_hashes) == 6

    assert manifest.entities_summary["database_tables"] == 2
    assert manifest.entities_summary["agent_profiles"] == 1
    assert manifest.entities_summary["custom_skills"] == 1
    assert manifest.entities_summary["cron_schedules"] == 1
    assert manifest.entities_summary["memory_records"] == 1


def test_full_stack_exporter_credential_scrubbing() -> None:
    """测试敏感凭据脱敏：包含 api_key、token、secret 的键被自动替换为 REDACTED。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")

    agent_with_secrets = {
        "finance_bot": json.dumps({
            "name": "Finance Agent",
            "openai_api_key": "sk-proj-super-secret-12345",
            "access_token": "bearer-token-abc",
            "webhook_secret": "whsec_xyz",
            "safe_param": "regular_value",
        }),
    }

    bundle = exporter.export_snapshot(
        backup_id="bak_scrubbed_002",
        database_tables={},
        agent_profiles=agent_with_secrets,
        custom_skills={},
        cron_schedules={},
        memory_records={},
        scrub_credentials=True,
    )

    scrubbed_json = bundle.agent_profiles["finance_bot"]
    parsed = json.loads(scrubbed_json)

    assert parsed["openai_api_key"] == REDACTED_PLACEHOLDER
    assert parsed["access_token"] == REDACTED_PLACEHOLDER
    assert parsed["webhook_secret"] == REDACTED_PLACEHOLDER
    assert parsed["safe_param"] == "regular_value"
    assert bundle.manifest.is_scrubbed is True


def test_full_stack_exporter_disable_scrubbing_preserves_raw() -> None:
    """测试关闭脱敏时完整保留原始凭据。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")

    raw_data = {
        "bot": json.dumps({"api_key": "raw_secret_key"}),
    }

    bundle = exporter.export_snapshot(
        backup_id="bak_raw_003",
        database_tables={},
        agent_profiles=raw_data,
        custom_skills={},
        cron_schedules={},
        memory_records={},
        scrub_credentials=False,
    )

    parsed = json.loads(bundle.agent_profiles["bot"])
    assert parsed["api_key"] == "raw_secret_key"
    assert bundle.manifest.is_scrubbed is False


def test_incremental_backup_computes_diff_and_reduces_size() -> None:
    """测试差异增量备份：仅包含发生修改或新增的项目，未修改项目被剔除。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")

    # 1. 基础全量备份 Base
    base_bundle = exporter.export_snapshot(
        backup_id="bak_base_010",
        database_tables={"users": "users_data_v1", "orders": "orders_data_v1"},
        agent_profiles={"coder": "coder_profile_v1"},
        custom_skills={"tools.py": "def f(): pass"},
        cron_schedules={"daily": "0 9 * * *"},
        memory_records={"pref": "short answers"},
    )

    # 2. 当前状态：users 未修改，orders 修改为 v2，新增 agent 'tester'
    current_bundle = exporter.export_snapshot(
        backup_id="bak_current_011",
        database_tables={"users": "users_data_v1", "orders": "orders_data_v2"},
        agent_profiles={"coder": "coder_profile_v1", "tester": "tester_profile_v1"},
        custom_skills={"tools.py": "def f(): pass"},
        cron_schedules={"daily": "0 9 * * *"},
        memory_records={"pref": "short answers"},
    )

    # 3. 计算增量
    inc_bundle = IncrementalBackupEngine.compute_incremental_diff(
        current_bundle=current_bundle,
        base_manifest=base_bundle.manifest,
        new_backup_id="bak_inc_012",
    )

    inc_manifest = inc_bundle.manifest
    assert inc_manifest.is_incremental is True
    assert inc_manifest.base_backup_id == "bak_base_010"

    # 验证未改动项目被剔除：users 未修改 -> 不在增量包中
    assert "users" not in inc_bundle.database_tables
    # orders 修改为 v2 -> 在增量包中
    assert inc_bundle.database_tables["orders"] == "orders_data_v2"
    # coder 未修改 -> 不在增量包中
    assert "coder" not in inc_bundle.agent_profiles
    # tester 为新增 -> 在增量包中
    assert inc_bundle.agent_profiles["tester"] == "tester_profile_v1"

    # 增量包总文件数远小于全量包（仅 2 个变动文件）
    assert len(inc_manifest.file_hashes) == 2
    assert inc_manifest.metadata["added_count"] == "1"
    assert inc_manifest.metadata["modified_count"] == "1"
    assert inc_manifest.metadata["unchanged_count"] == "5"


def test_disaster_recovery_preflight_valid_bundle() -> None:
    """测试正常备份包顺利通过灾难恢复 Preflight 校验。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")
    bundle = exporter.export_snapshot(
        backup_id="bak_valid_020",
        database_tables={"t1": "data1"},
        agent_profiles={"a1": "agent1"},
        custom_skills={},
        cron_schedules={},
        memory_records={},
    )

    report = DisasterRecoveryWizard.preflight_validate(bundle, current_app_version="0.21.0")

    assert report.is_valid is True
    assert report.checksum_verified is True
    assert report.schema_compatible is True
    assert len(report.error_reasons) == 0


def test_disaster_recovery_preflight_tampered_bundle_rejected() -> None:
    """测试篡改后的备份包签名校验失败并被拦截。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")
    bundle = exporter.export_snapshot(
        backup_id="bak_tamper_030",
        database_tables={"t1": "clean_data"},
        agent_profiles={},
        custom_skills={},
        cron_schedules={},
        memory_records={},
    )

    # 恶意篡改内容
    tampered_bundle = BackupArchiveBundle(
        manifest=bundle.manifest,
        database_tables={"t1": "malicious_injected_data"},
        agent_profiles=bundle.agent_profiles,
        custom_skills=bundle.custom_skills,
        cron_schedules=bundle.cron_schedules,
        memory_records=bundle.memory_records,
    )

    report = DisasterRecoveryWizard.preflight_validate(tampered_bundle, current_app_version="0.21.0")

    assert report.is_valid is False
    assert report.checksum_verified is False
    assert any("Checksum verification failed" in err for err in report.error_reasons)


def test_disaster_recovery_preflight_incompatible_major_version() -> None:
    """测试主版本越级倒退时被 Preflight 拦截。"""
    manifest = BackupManifest(
        manifest_version=1,
        app_version="2.0.0",  # 来自遥远的未来主版本
        backup_id="bak_future_040",
        created_at=1000.0,
        is_incremental=False,
        base_backup_id=None,
        checksum="dummy",
        file_hashes={},
        entities_summary={},
    )
    bundle = BackupArchiveBundle(
        manifest=manifest,
        database_tables={},
        agent_profiles={},
        custom_skills={},
        cron_schedules={},
        memory_records={},
    )

    report = DisasterRecoveryWizard.preflight_validate(bundle, current_app_version="1.2.0")

    assert report.is_valid is False
    assert any("Incompatible version" in err for err in report.error_reasons)


def test_disaster_recovery_restore_dry_run_mode() -> None:
    """测试 Dry-run 演练模式：评估恢复影响，绝不修改目标存储。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")
    bundle = exporter.export_snapshot(
        backup_id="bak_dryrun_050",
        database_tables={"users": "users_data"},
        agent_profiles={"bot1": "bot_data"},
        custom_skills={"tool.py": "tool_data"},
        cron_schedules={},
        memory_records={},
    )

    target_stores: MutableMapping[str, MutableMapping[str, str]] = {
        "db": {"old_db": "old"},
        "agent": {},
        "skill": {},
        "cron": {},
        "mem": {},
    }

    result = DisasterRecoveryWizard.restore(
        bundle=bundle,
        target_stores=target_stores,
        current_app_version="0.21.0",
        dry_run=True,
    )

    assert result.success is True
    assert result.is_dry_run is True
    assert result.total_files_restored == 3
    # 目标存储保持原样，未被改动
    assert target_stores["db"] == {"old_db": "old"}
    assert "users" not in target_stores["db"]


def test_disaster_recovery_restore_atomic_execution() -> None:
    """测试真实恢复执行：目标存储被原子回填写入。"""
    exporter = FullStackSnapshotExporter(app_version="0.21.0")
    bundle = exporter.export_snapshot(
        backup_id="bak_real_060",
        database_tables={"users": "restored_users"},
        agent_profiles={"assistant": "restored_assistant"},
        custom_skills={},
        cron_schedules={"daily": "restored_daily"},
        memory_records={},
    )

    target_stores: MutableMapping[str, MutableMapping[str, str]] = {
        "db": {"original_db": "original"},
        "agent": {},
        "skill": {},
        "cron": {},
        "mem": {},
    }

    result = DisasterRecoveryWizard.restore(
        bundle=bundle,
        target_stores=target_stores,
        current_app_version="0.21.0",
        dry_run=False,
    )

    assert result.success is True
    assert result.is_dry_run is False
    assert result.total_files_restored == 3
    assert target_stores["db"]["users"] == "restored_users"
    assert target_stores["agent"]["assistant"] == "restored_assistant"
    assert target_stores["cron"]["daily"] == "restored_daily"
    assert target_stores["db"]["original_db"] == "original"  # 原有无冲突数据保留
