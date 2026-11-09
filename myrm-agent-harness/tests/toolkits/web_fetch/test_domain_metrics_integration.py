"""域名级学习数据集成测试

验证：
1. DomainMetrics 数据模型（失败时间衰减、SMART 等待策略数据、序列化）
2. DomainMetricsManager 持久化、LRU 驱逐、不活跃清理、使用时触发的定时保存与清理
3. 任何记录都会刷新域名活跃时间（活跃域名不会被清理）
4. 云沙箱文件锁机制
5. domain_key 域名键
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType
from myrm_agent_harness.toolkits.web_fetch.router import DomainMetricsManager
from myrm_agent_harness.toolkits.web_fetch.router.models import DomainMetrics, domain_key

_DAY = 86400


class TestDomainMetrics:
    """DomainMetrics 数据模型测试"""

    def test_initialization(self):
        """测试初始化和默认值"""
        metrics = DomainMetrics(domain="example.com")

        assert metrics.domain == "example.com"
        assert metrics.networkidle_success_count == 0
        assert metrics.networkidle_fail_count == 0

        for ft in FetcherType:
            assert ft in metrics.failure_timestamps
            assert metrics.get_recent_failures_count(ft) == 0

    def test_record_failure(self):
        """测试按层级记录失败"""
        metrics = DomainMetrics(domain="example.com")

        metrics.record_failure(FetcherType.HTTP)

        assert metrics.get_recent_failures_count(FetcherType.HTTP) == 1
        assert metrics.get_recent_failures_count(FetcherType.BROWSER) == 0

    def test_time_decay_failures(self):
        """测试时间衰减失败计数"""
        metrics = DomainMetrics(domain="example.com")

        now = time.time()
        metrics.failure_timestamps[FetcherType.HTTP].append(now - 25 * 3600)
        metrics.failure_timestamps[FetcherType.HTTP].append(now - 23 * 3600)
        metrics.failure_timestamps[FetcherType.HTTP].append(now - 1 * 3600)

        recent_count = metrics.get_recent_failures_count(FetcherType.HTTP, window_hours=24)
        assert recent_count == 2

    @pytest.mark.parametrize(
        "record",
        [
            lambda m: m.record_failure(FetcherType.HTTP),
            lambda m: m.record_wait_strategy("networkidle", 100),
            lambda m: m.record_networkidle_result(success=True),
        ],
        ids=["failure", "wait-strategy", "networkidle-result"],
    )
    def test_every_record_marks_the_domain_active(self, record: Callable[[DomainMetrics], None]):
        """任何记录都刷新 last_access，否则只走浏览器的活跃域名会被当作不活跃清理"""
        metrics = DomainMetrics(domain="example.com")
        metrics.last_access = 0.0

        record(metrics)

        assert time.time() - metrics.last_access < 5

    def test_smart_fast_timeout_calculation(self):
        """测试 SMART 策略 fast_timeout 计算"""
        metrics = DomainMetrics(domain="fast.com")

        for _ in range(25):
            metrics.record_networkidle_result(success=True)
            metrics.record_wait_strategy("networkidle", 200)

        timeout = metrics.get_smart_fast_timeout()
        assert timeout is not None
        assert 200 <= timeout <= 500

    def test_smart_fast_timeout_skip_low_success_rate(self):
        """测试低成功率时跳过快速路径"""
        metrics = DomainMetrics(domain="slow.com")

        for _ in range(25):
            metrics.record_networkidle_result(success=False)

        timeout = metrics.get_smart_fast_timeout()
        assert timeout is None

    def test_serialization_round_trip(self):
        """测试序列化往返保留全部学习数据"""
        metrics = DomainMetrics(domain="example.com")
        metrics.record_failure(FetcherType.STEALTH)
        metrics.record_wait_strategy("networkidle", 150)
        metrics.record_networkidle_result(success=False)

        restored = DomainMetrics.from_dict(json.loads(json.dumps(metrics.to_dict())))

        assert restored.domain == "example.com"
        assert restored.get_recent_failures_count(FetcherType.STEALTH) == 1
        assert restored.get_recent_failures_count(FetcherType.HTTP) == 0
        assert list(restored.wait_strategy_latencies["networkidle"]) == [150.0]
        assert restored.networkidle_fail_count == 1
        assert restored.last_access == metrics.last_access

    def test_persisted_data_with_unknown_keys_still_loads(self):
        """已落盘的数据含本模型不再记录的字段（逐层级延迟/计数）时，共享的学习数据照常恢复"""
        persisted = {
            "domain": "old.com",
            "fetcher_latencies": {"HTTP": [100.0]},
            "fetcher_success_latencies": {"HTTP": [100.0]},
            "fetcher_success_counts": {"HTTP": 3},
            "fetcher_total_counts": {"HTTP": 4},
            "total_accesses": 4,
            "networkidle_success_count": 7,
            "failure_timestamps": {"HTTP": [time.time()]},
            "last_access": 123.0,
        }

        restored = DomainMetrics.from_dict(persisted)

        assert restored.networkidle_success_count == 7
        assert restored.get_recent_failures_count(FetcherType.HTTP) == 1
        assert restored.get_recent_failures_count(FetcherType.STEALTH) == 0
        assert restored.last_access == 123.0
        restored.record_failure(FetcherType.STEALTH)  # 持久化数据缺的层级队列也已就绪


class TestDomainMetricsManager:
    """DomainMetricsManager 持久化和管理测试"""

    def test_local_storage(self):
        """测试本地存储"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_metrics.json"

            manager = DomainMetricsManager(storage_path=storage_path, use_file_lock=False)
            manager.record_failure("example.com", FetcherType.HTTP)
            manager._save_metrics()

            manager2 = DomainMetricsManager(storage_path=storage_path, use_file_lock=False)

            loaded_metrics = manager2.get("example.com")
            assert loaded_metrics is not None
            assert loaded_metrics.get_recent_failures_count(FetcherType.HTTP) == 1

    def test_explicit_file_lock_enable(self):
        """测试显式启用文件锁"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "test_metrics.json"

            manager = DomainMetricsManager(storage_path=storage_path, use_file_lock=True)
            assert manager._use_file_lock is True

    def test_explicit_path_override(self):
        """测试显式路径参数覆盖"""
        with tempfile.TemporaryDirectory() as tmpdir:
            explicit_path = Path(tmpdir) / "custom_metrics.json"
            manager = DomainMetricsManager(storage_path=explicit_path)
            assert manager._storage_path == explicit_path

    def test_record_failure_creates_the_domain(self, tmp_path: Path):
        """首次失败的域名自动建档"""
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json")
        assert manager.get("new.com") is None

        manager.record_failure("new.com", FetcherType.BROWSER)

        metrics = manager.get("new.com")
        assert metrics is not None
        assert metrics.get_recent_failures_count(FetcherType.BROWSER) == 1


class TestConcurrencySafety:
    """并发安全测试"""

    def test_domain_metrics_concurrent_writes(self):
        """测试 DomainMetrics 并发写入"""
        metrics = DomainMetrics(domain="concurrent.com")
        errors: list[Exception] = []

        def writer():
            try:
                for _ in range(100):
                    metrics.record_networkidle_result(success=True)
                    metrics.record_failure(FetcherType.HTTP)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert metrics.networkidle_success_count == 1000
        assert metrics.get_recent_failures_count(FetcherType.HTTP) == 100  # 失败时间戳保留最近 100 条


class TestLRUEviction:
    """测试 LRU 驱逐机制"""

    def test_lru_eviction_when_max_domains_exceeded(self):
        """测试超过 max_domains 时 LRU 驱逐最久未访问的域名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DomainMetricsManager(storage_path=f"{tmpdir}/metrics.json", max_domains=10)

            for i in range(10):
                manager.record_failure(f"domain{i}.com", FetcherType.HTTP)
                time.sleep(0.01)

            oldest_domain = "domain0.com"
            oldest_metrics = manager.get(oldest_domain)
            assert oldest_metrics is not None

            time.sleep(0.05)
            manager.record_failure("domain10.com", FetcherType.HTTP)

            assert len(manager._metrics) == 10
            assert manager.get(oldest_domain) is None
            assert manager.get("domain1.com") is not None
            assert manager.get("domain10.com") is not None


class TestCleanupInactive:
    """测试清理不活跃域名"""

    def test_cleanup_inactive_domains(self):
        """测试清理长期未访问的域名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = DomainMetricsManager(storage_path=f"{tmpdir}/metrics.json")

            manager.record_failure("active.com", FetcherType.HTTP)

            inactive_metrics = manager.get_or_create("inactive.com")
            inactive_metrics.last_access = time.time() - 31 * _DAY

            assert len(manager._metrics) == 2

            manager.cleanup_inactive_domains()

            assert len(manager._metrics) == 1
            assert manager.get("active.com") is not None
            assert manager.get("inactive.com") is None

    def test_a_recorded_failure_keeps_the_domain_from_being_cleaned_up(self, tmp_path: Path):
        """记录过失败的域名算活跃，即使它的档案是 8 天前建的"""
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json", inactive_days=7)
        manager.get_or_create("old.com").last_access = time.time() - 8 * _DAY

        manager.record_failure("old.com", FetcherType.HTTP)
        manager.cleanup_inactive_domains()

        assert manager.get("old.com") is not None


class TestScheduledMaintenance:
    """保存与清理由域名学习库的使用驱动，没有别的定时器"""

    def test_save_is_requested_once_the_interval_has_elapsed(self, tmp_path: Path):
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json", save_interval_minutes=5)
        manager._last_save_time = time.time() - 6 * 60

        with patch.object(manager, "request_save") as request_save:
            manager.get_or_create("a.com")
            manager.get_or_create("b.com")

        request_save.assert_called_once_with()

    def test_save_waits_for_its_interval(self, tmp_path: Path):
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json", save_interval_minutes=5)
        manager._last_save_time = time.time() - 4 * 60

        with patch.object(manager, "request_save") as request_save:
            manager.get_or_create("a.com")

        request_save.assert_not_called()

    def test_inactive_domains_are_cleaned_up_hourly(self, tmp_path: Path):
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json", inactive_days=7)
        manager.get_or_create("stale.com").last_access = time.time() - 8 * _DAY
        manager._last_cleanup_time = time.time() - 3601

        manager.get_or_create("fresh.com")

        assert manager.get("stale.com") is None
        assert manager.get("fresh.com") is not None

    def test_cleanup_waits_for_its_interval(self, tmp_path: Path):
        manager = DomainMetricsManager(storage_path=tmp_path / "metrics.json", inactive_days=7)
        manager.get_or_create("stale.com").last_access = time.time() - 8 * _DAY
        manager._last_cleanup_time = time.time() - 3500

        manager.get_or_create("fresh.com")

        assert manager.get("stale.com") is not None


class TestFileLock:
    """测试文件锁机制"""

    @pytest.mark.parametrize("use_file_lock", [True, False])
    def test_file_lock_modes_save_and_reload(self, use_file_lock: bool):
        """文件锁启用/禁用时保存、重新加载都正常"""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = f"{tmpdir}/metrics.json"
            manager = DomainMetricsManager(storage_path=storage_path, use_file_lock=use_file_lock)

            assert manager._use_file_lock is use_file_lock

            manager.record_failure("test.com", FetcherType.HTTP)
            manager._save_metrics()

            reloaded = DomainMetricsManager(storage_path=storage_path, use_file_lock=use_file_lock)
            assert reloaded.get("test.com") is not None


class TestDomainKey:
    """域名键：同一站点的不同写法落到同一个键，无法解析的输入也有稳定的键"""

    @pytest.mark.parametrize(
        ("url", "key"),
        [
            ("https://Example.COM/a?b=1", "example.com"),
            ("http://example.com:8080/x", "example.com:8080"),
            ("https://www.example.com/", "www.example.com"),
            ("not-a-url", "not-a-url"),
            ("://invalid", "://invalid"),
            ("", ""),
            ("http://", "http://"),
            ("https://", "https://"),
            ("HTTP://[BAD", "http://[bad"),
        ],
        ids=[
            "case-folded",
            "port-kept",
            "www-kept",
            "bare-text",
            "no-scheme",
            "empty",
            "http-no-host",
            "https-no-host",
            "unparsable",
        ],
    )
    def test_domain_key(self, url: str, key: str):
        assert domain_key(url) == key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
