from datetime import UTC, datetime

from app.api.statistics.context_health import build_chat_compaction_snapshot, build_context_health


def test_build_context_health_prefers_runtime_compaction_metrics() -> None:
    message_stats = {
        "calls": 4,
        "inputTokens": 12_000,
        "cachedTokens": 5_400,
        "cacheHitRate": 0.45,
    }
    task_metrics = {
        "compression_count": 3,
        "total_tokens_saved": 8_000,
        "net_tokens_saved": 7_500,
        "compression_efficiency": 0.4,
        "refetch_count": 0,
        "refetch_ratio": 0.0,
        "compression_events": [
            {"dedup_tokens_saved": 600, "integrity_skipped": 0},
            {"dedup_tokens_saved": 400, "integrity_skipped": 0},
        ],
        "archive_count": 2,
        "soft_trimmed_count": 1,
        "offload_failed_count": 0,
        "archive_written_count": 1,
        "archive_reused_count": 1,
        "archive_bytes_written": 2048,
        "archive_bytes_reused": 2048,
        "archive_refetch_count": 0,
        "archive_refetch_tokens": 0,
        "archive_restore_requested_count": 0,
        "archive_restore_allowed_count": 0,
        "archive_restore_blocked_count": 0,
        "archive_restore_result_count": 1,
        "archive_restore_result_tokens": 250,
        "archive_restore_result_lines": 20,
        "archive_restore_result_bytes": 1024,
        "archived_original_tokens": 6_000,
        "pruning_tokens_saved": 2_500,
        "pruning_net_tokens_saved": 2_250,
    }
    chat_snapshot = build_chat_compaction_snapshot(
        compacted_at=datetime(2026, 4, 18, tzinfo=UTC),
        compacted_tokens_saved=2_000,
    )

    health = build_context_health(
        message_stats=message_stats,
        task_metrics=task_metrics,
        chat_compaction=chat_snapshot,
    )

    assert health.status == "healthy"
    assert health.compaction.status == "healthy"
    assert health.compaction.tokens_saved == 8_000
    assert health.compaction.dedup_tokens_saved == 1_000
    assert health.pruning.status == "healthy"
    assert health.pruning.archived == 2
    assert health.pruning.archive_written_count == 1
    assert health.pruning.archive_reused_count == 1
    assert health.pruning.archive_bytes_written == 2048
    assert health.pruning.archive_bytes_reused == 2048
    assert health.pruning.deferred_count == 0
    assert health.pruning.archive_restore_requested_count == 0
    assert health.pruning.archive_restore_allowed_count == 0
    assert health.pruning.archive_restore_blocked_ratio == 0.0
    assert health.pruning.archive_restore_result_count == 1
    assert health.pruning.archive_restore_result_tokens == 250
    assert health.pruning.archive_restore_result_lines == 20
    assert health.pruning.archive_restore_result_bytes == 1024
    assert health.pruning.pruning_restore_cost_ratio == 0.1
    assert health.pruning.pruning_restore_roi_ratio == 0.9
    assert health.pruning.tokens_saved == 2_500
    assert health.pruning.net_tokens_saved == 2_250
    assert health.pruning.backoff_applied is False
    assert health.pruning.backoff_reasons == {}
    assert health.cache.status == "healthy"
    assert health.cache.retention_observation_state == "observed"
    assert health.cache.observed_cached_tokens == 5_400
    assert health.cache.observation_sample_source == "session_aggregate"
    assert health.cache.observed_cache_hit_rate == 0.45


def test_build_context_health_uses_persisted_summary_when_runtime_metrics_absent() -> None:
    message_stats = {
        "calls": 1,
        "inputTokens": 1_200,
        "cachedTokens": 0,
        "cacheHitRate": 0.0,
    }
    chat_snapshot = build_chat_compaction_snapshot(
        compacted_at=datetime(2026, 4, 18, tzinfo=UTC),
        compacted_tokens_saved=1_500,
    )

    health = build_context_health(
        message_stats=message_stats,
        task_metrics={},
        chat_compaction=chat_snapshot,
    )

    assert health.status == "healthy"
    assert health.compaction.active is True
    assert health.compaction.tokens_saved == 1_500
    assert health.compaction.summary_persisted is True
    assert health.pruning.status == "inactive"
    assert health.cache.status == "inactive"
    assert health.cache.retention_observation_state == "insufficient_data"


def test_build_context_health_flags_cache_break_and_compaction_instability() -> None:
    message_stats = {
        "calls": 3,
        "inputTokens": 10_000,
        "cachedTokens": 0,
        "cacheHitRate": 0.0,
    }
    task_metrics = {
        "compression_count": 2,
        "total_tokens_saved": 3_000,
        "net_tokens_saved": 500,
        "compression_efficiency": 0.03,
        "refetch_count": 2,
        "refetch_ratio": 0.5,
        "compression_events": [
            {"dedup_tokens_saved": 0, "integrity_skipped": 1},
            {
                "compression_type": "cache_ttl_prune",
                "offload_failure_kinds": {"temporary_failure": 2},
            },
        ],
        "archive_count": 1,
        "soft_trimmed_count": 0,
        "offload_failed_count": 1,
        "archive_refetch_count": 0,
        "archive_refetch_tokens": 0,
        "archive_restore_requested_count": 2,
        "archive_restore_allowed_count": 1,
        "archive_restore_blocked_count": 1,
        "archive_restore_block_events": [
            {
                "timestamp": "2026-05-19T00:00:00+00:00",
                "reason": "archive_restore_range_required",
                "estimated_tokens": 2_500,
                "archive_path": ".context/chat/compacted/result.txt",
                "message": "Full archive restore blocked.",
                "suggested_action": "Read a targeted line range from chunk_restore_args.",
                "reason_label_key": "archive_restore_range_required",
                "severity": "warning",
                "primary_restore_arg": ".context/chat/compacted/result.txt:1-200",
                "recommended_ranges": [
                    ".context/chat/compacted/result.txt:1-200",
                    ".context/chat/compacted/result.txt:201-400",
                ],
                "restore_range_hints": [
                    {
                        "range_arg": ".context/chat/compacted/result.txt:1-200",
                        "reason": "error_keyword",
                        "start_line": 1,
                        "end_line": 200,
                        "line": 40,
                    }
                ],
                "content_features": [
                    {
                        "feature_type": "json_keys",
                        "count": 3,
                        "values": ["status", "errors"],
                    }
                ],
            }
        ],
        "offload_failure_kinds": {"quota_exceeded": 1},
    }

    health = build_context_health(
        message_stats=message_stats,
        task_metrics=task_metrics,
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.status == "critical"
    assert health.compaction.status == "critical"
    assert health.pruning.status == "warning"
    assert health.pruning.archive_restore_requested_count == 2
    assert health.pruning.archive_restore_allowed_count == 1
    assert health.pruning.archive_restore_blocked_count == 1
    assert health.pruning.archive_restore_blocked_ratio == 0.5
    assert health.pruning.archive_restore_block_events[0].reason == "archive_restore_range_required"
    assert health.pruning.archive_restore_block_events[0].suggested_action.endswith("chunk_restore_args.")
    assert health.pruning.archive_restore_block_events[0].reason_label_key == "archive_restore_range_required"
    assert health.pruning.archive_restore_block_events[0].primary_restore_arg == (".context/chat/compacted/result.txt:1-200")
    assert health.pruning.archive_restore_block_events[0].recommended_ranges == [
        ".context/chat/compacted/result.txt:1-200",
        ".context/chat/compacted/result.txt:201-400",
    ]
    assert health.pruning.archive_restore_block_events[0].restore_range_hints[0].reason == "error_keyword"
    assert health.pruning.archive_restore_block_events[0].restore_range_hints[0].line == 40
    assert health.pruning.archive_restore_block_events[0].content_features[0].feature_type == "json_keys"
    assert health.pruning.archive_restore_block_events[0].content_features[0].values == ["status", "errors"]
    assert health.pruning.offload_failure_kinds == {
        "quota_exceeded": 1,
        "temporary_failure": 2,
    }
    assert health.cache.status == "critical"
    assert health.cache.retention_observation_state == "estimated"


def test_build_context_health_uses_dominant_model_cache_sample() -> None:
    message_stats = {
        "calls": 5,
        "inputTokens": 20_000,
        "cachedTokens": 0,
        "cacheHitRate": 0.0,
        "modelBreakdown": {
            "gpt-4.1": {
                "calls": 3,
                "inputTokens": 12_000,
                "cachedTokens": 6_000,
            },
            "fallback-model": {
                "calls": 2,
                "inputTokens": 8_000,
                "cachedTokens": 0,
            },
        },
    }

    health = build_context_health(
        message_stats=message_stats,
        task_metrics={},
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
        model_name="gpt-4.1",
    )

    assert health.cache.status == "healthy"
    assert health.cache.cache_hit_rate == 0.0
    assert health.cache.observation_sample_source == "dominant_model"
    assert health.cache.observation_model_name == "gpt-4.1"
    assert health.cache.observed_calls == 3
    assert health.cache.observed_input_tokens == 12_000
    assert health.cache.observed_cached_tokens == 6_000
    assert health.cache.observed_cache_hit_rate == 0.5
    assert health.cache.retention_observation_state == "observed"


def test_build_context_health_uses_normalized_exact_model_cache_sample() -> None:
    message_stats = {
        "calls": 5,
        "inputTokens": 20_000,
        "cachedTokens": 0,
        "cacheHitRate": 0.0,
        "modelBreakdown": {
            "openai/gpt-4.1": {
                "calls": 3,
                "inputTokens": 12_000,
                "cachedTokens": 6_000,
            },
            "fallback-model": {
                "calls": 2,
                "inputTokens": 8_000,
                "cachedTokens": 0,
            },
        },
    }

    health = build_context_health(
        message_stats=message_stats,
        task_metrics={},
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
        model_name="gpt-4.1",
    )

    assert health.cache.status == "healthy"
    assert health.cache.observation_sample_source == "dominant_model"
    assert health.cache.observation_model_name == "openai/gpt-4.1"
    assert health.cache.observed_cache_hit_rate == 0.5


def test_build_context_health_uses_aggregate_when_normalized_model_match_is_ambiguous() -> None:
    message_stats = {
        "calls": 5,
        "inputTokens": 20_000,
        "cachedTokens": 0,
        "cacheHitRate": 0.0,
        "modelBreakdown": {
            "openai/gpt-4.1": {
                "calls": 3,
                "inputTokens": 12_000,
                "cachedTokens": 6_000,
            },
            "azure/gpt-4.1": {
                "calls": 2,
                "inputTokens": 8_000,
                "cachedTokens": 4_000,
            },
        },
    }

    health = build_context_health(
        message_stats=message_stats,
        task_metrics={},
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
        model_name="gpt-4.1",
    )

    assert health.cache.status == "critical"
    assert health.cache.observation_sample_source == "session_aggregate"
    assert health.cache.observation_model_name == ""


def test_build_context_health_falls_back_to_prune_event_fields() -> None:
    task_metrics = {
        "compression_events": [
            {
                "compression_type": "cache_ttl_prune",
                "archive_count": 3,
                "soft_trimmed_count": 2,
                "offload_failed_count": 0,
                "archive_written_count": 1,
                "archive_reused_count": 2,
                "archive_bytes_written": 1024,
                "archive_bytes_reused": 2048,
                "deferred_count": 2,
                "deferred_reasons": {"archive_count_budget": 2},
                "archive_deferred_count": 3,
                "archive_deferred_reasons": {"offload_bytes_budget": 3},
                "archive_deferred_soft_trimmed_count": 2,
                "archive_deferred_soft_trimmed_reasons": {"offload_bytes_budget": 2},
                "original_tokens": 9_000,
                "backoff_applied": True,
                "backoff_reasons": ["high_refetch_ratio"],
                "effective_soft_trim_ratio": 0.4,
                "effective_hard_clear_ratio": 0.6,
                "effective_min_prunable_tokens": 25_000,
            }
        ],
        "archive_refetch_count": 1,
        "archive_refetch_tokens": 400,
    }

    health = build_context_health(
        message_stats={},
        task_metrics=task_metrics,
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.status == "warning"
    assert health.pruning.archived == 3
    assert health.pruning.soft_trimmed == 2
    assert health.pruning.archive_written_count == 1
    assert health.pruning.archive_reused_count == 2
    assert health.pruning.archive_bytes_written == 1024
    assert health.pruning.archive_bytes_reused == 2048
    assert health.pruning.deferred_count == 2
    assert health.pruning.deferred_reasons == {"archive_count_budget": 2}
    assert health.pruning.archive_deferred_count == 3
    assert health.pruning.archive_deferred_reasons == {"offload_bytes_budget": 3}
    assert health.pruning.archive_deferred_soft_trimmed_count == 2
    assert health.pruning.original_tokens == 9_000
    assert health.pruning.tokens_saved == 0
    assert health.pruning.net_tokens_saved == -400
    assert health.pruning.refetch_ratio == 0.2
    assert health.pruning.backoff_applied is True
    # Explicit prune-event backoff contract wins; do not infer extra reasons.
    assert health.pruning.backoff_reasons == {"high_refetch_ratio": 1}
    assert health.pruning.effective_soft_trim_ratio == 0.4
    assert health.pruning.effective_hard_clear_ratio == 0.6
    assert health.pruning.effective_min_prunable_tokens == 25_000


def test_build_context_health_flags_negative_pruning_savings() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_count": 1,
            "soft_trimmed_count": 0,
            "offload_failed_count": 0,
            "archive_refetch_count": 2,
            "archive_refetch_tokens": 900,
            "archive_restore_blocked_count": 1,
            "archived_original_tokens": 2_000,
            "pruning_tokens_saved": 500,
            "pruning_net_tokens_saved": -400,
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.status == "warning"
    assert health.pruning.net_tokens_saved == -400
    assert health.pruning.refetch_ratio == 2.0
    assert health.pruning.archive_restore_blocked_count == 1


def test_build_context_health_uses_restore_outcomes_as_counter_source() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_restore_requested_count": 99,
            "archive_restore_allowed_count": 99,
            "archive_restore_blocked_count": 99,
            "archive_restore_outcome_events": [
                {"outcome": "allowed", "archive_path": ".context/chat/one.txt"},
                {"outcome": "blocked", "archive_path": ".context/chat/two.txt"},
                {"outcome": "blocked", "archive_path": ".context/chat/three.txt"},
                {"outcome": "ignored", "archive_path": ".context/chat/ignored.txt"},
                "invalid",
            ],
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.archive_restore_requested_count == 3
    assert health.pruning.archive_restore_allowed_count == 1
    assert health.pruning.archive_restore_blocked_count == 2
    assert health.pruning.archive_restore_blocked_ratio == 2 / 3


def test_build_context_health_uses_restore_result_events_as_counter_source() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_restore_result_count": 99,
            "archive_restore_result_tokens": 99,
            "archive_restore_result_lines": 99,
            "archive_restore_result_bytes": 99,
            "archive_restore_result_events": [
                {
                    "estimated_tokens": 120,
                    "restored_line_count": 3,
                    "restored_bytes": 512,
                },
                {
                    "estimated_tokens": 80,
                    "restored_line_count": 2,
                    "restored_bytes": 256,
                },
                "invalid",
            ],
            "pruning_tokens_saved": 1_000,
            "pruning_net_tokens_saved": 800,
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.archive_restore_result_count == 2
    assert health.pruning.archive_restore_result_tokens == 200
    assert health.pruning.archive_restore_result_lines == 5
    assert health.pruning.archive_restore_result_bytes == 768
    assert health.pruning.pruning_restore_cost_ratio == 0.2
    assert health.pruning.pruning_restore_roi_ratio == 0.8


def test_build_context_health_warns_when_restore_cost_consumes_pruning_savings() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_count": 1,
            "archive_restore_result_events": [
                {
                    "estimated_tokens": 700,
                    "restored_line_count": 30,
                    "restored_bytes": 4096,
                }
            ],
            "pruning_tokens_saved": 1_000,
            "pruning_net_tokens_saved": 300,
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.status == "warning"
    assert health.status == "warning"
    assert health.pruning.archive_restore_result_tokens == 700
    assert health.pruning.pruning_restore_cost_ratio == 0.7
    assert health.pruning.pruning_restore_roi_ratio == 0.3
    assert health.pruning.backoff_applied is True
    assert health.pruning.backoff_reasons == {
        "high_restore_cost_ratio": 1,
        "low_restore_roi_ratio": 1,
    }


def test_build_context_health_does_not_infer_restore_counters_from_block_events() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_restore_block_events": [
                {
                    "reason": "archive_restore_range_required",
                    "archive_path": ".context/chat/large.txt",
                    "estimated_tokens": 12_000,
                }
            ],
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.archive_restore_requested_count == 0
    assert health.pruning.archive_restore_allowed_count == 0
    assert health.pruning.archive_restore_blocked_count == 0
    assert health.pruning.archive_restore_blocked_ratio == 0.0
    assert len(health.pruning.archive_restore_block_events) == 1


def test_build_context_health_includes_archive_summary_metrics() -> None:
    health = build_context_health(
        message_stats={},
        task_metrics={
            "archive_summary": {
                "queued_count": 2,
                "succeeded_count": 1,
                "failed_count": 0,
                "skipped_count": 1,
                "skipped_reasons": {"store_unavailable": 1},
            },
        },
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.archive_summary_queued_count == 2
    assert health.pruning.archive_summary_succeeded_count == 1
    assert health.pruning.archive_summary_skipped_count == 1
    assert health.pruning.archive_summary_skipped_reasons == {"store_unavailable": 1}
    assert health.pruning.active is True
