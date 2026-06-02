/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SessionContextHealthPanel from '../sections/SessionContextHealthPanel';
import useChatStore from '@/store/useChatStore';
import type { ContextHealth } from '@/services/contextHealth';

function renderPanel(health: ContextHealth) {
  return render(<SessionContextHealthPanel health={health} sessionId="session-1" />);
}

describe('SessionContextHealthPanel', () => {
  const originalSendMessage = useChatStore.getState().sendMessage;

  beforeEach(() => {
    useChatStore.setState({ chatId: 'session-1', sendMessage: vi.fn<typeof originalSendMessage>() });
  });

  it('renders compaction and cache metrics', () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });

    renderPanel({
      status: 'warning',
      compaction: {
        status: 'healthy',
        active: true,
        count: 2,
        tokens_saved: 4200,
        net_tokens_saved: 4000,
        efficiency: 0.32,
        refetch_count: 0,
        refetch_ratio: 0,
        dedup_tokens_saved: 200,
        integrity_skipped: 0,
        summary_persisted: true,
        last_compacted_at: '2026-04-18T08:00:00+00:00',
      },
      pruning: {
        status: 'healthy',
        active: true,
        archived: 3,
        soft_trimmed: 1,
        offload_failed: 0,
        archive_written_count: 2,
        archive_reused_count: 1,
        archive_bytes_written: 4096,
        archive_bytes_reused: 2048,
        deferred_count: 2,
        deferred_reasons: {
          archive_count_budget: 2,
        },
        archive_deferred_count: 3,
        archive_deferred_reasons: {
          offload_bytes_budget: 3,
        },
        archive_deferred_soft_trimmed_count: 2,
        archive_deferred_soft_trimmed_reasons: {
          offload_bytes_budget: 2,
        },
        archive_refetch_count: 1,
        archive_refetch_tokens: 200,
        archive_restore_requested_count: 3,
        archive_restore_allowed_count: 2,
        archive_restore_blocked_count: 1,
        archive_restore_blocked_ratio: 0.3333,
        archive_restore_result_count: 1,
        archive_restore_result_tokens: 200,
        archive_restore_result_lines: 12,
        archive_restore_result_bytes: 1024,
        pruning_restore_cost_ratio: 0.1667,
        pruning_restore_roi_ratio: 0.8333,
        archive_restore_block_events: [
          {
            timestamp: '2026-05-19T00:00:00+00:00',
            reason: 'archive_restore_range_required',
            estimated_tokens: 2500,
            archive_path: '.context/chat/compacted/result.txt',
            message: 'Full archive restore blocked.',
            suggested_action: 'Read a targeted line range from chunk_restore_args.',
            reason_label_key: 'archive_restore_range_required',
            severity: 'warning',
            primary_restore_arg: '.context/chat/compacted/result.txt:1-200',
            recommended_ranges: [
              '.context/chat/compacted/result.txt:1-200',
              '.context/chat/compacted/result.txt:201-400',
            ],
            restore_range_hints: [
              {
                range_arg: '.context/chat/compacted/result.txt:1-200',
                reason: 'error_keyword',
                start_line: 1,
                end_line: 200,
                line: 40,
              },
              {
                range_arg: '.context/chat/compacted/result.txt:201-400',
                reason: 'code_block',
                start_line: 201,
                end_line: 400,
                line: 201,
              },
            ],
            content_features: [
              {
                feature_type: 'json_keys',
                count: 3,
                values: ['status', 'errors'],
              },
            ],
            guidance_source: 'restore_map',
            fallback_reason: '',
          },
        ],
        offload_failure_kinds: {
          quota_exceeded: 1,
        },
        original_tokens: 8200,
        tokens_saved: 1200,
        net_tokens_saved: 1000,
        refetch_ratio: 0.25,
        backoff_applied: true,
        backoff_reasons: {
          high_restore_cost_ratio: 1,
        },
        effective_soft_trim_ratio: 0.4,
        effective_hard_clear_ratio: 0.6,
        effective_min_prunable_tokens: 25000,
        archive_summary_queued_count: 2,
        archive_summary_succeeded_count: 1,
        archive_summary_failed_count: 0,
        archive_summary_skipped_count: 1,
        archive_summary_skipped_reasons: { low_value_archive: 1 },
      },
      cache: {
        status: 'warning',
        active: true,
        calls: 3,
        input_tokens: 9000,
        cached_tokens: 1500,
        cache_hit_rate: 0.166,
        model_family: 'openai',
        retention_mode: 'provider TTL profile: openai',
        ttl_seconds: 600,
        policy_reason: 'provider TTL profile: openai',
        policy_source_url: 'https://platform.openai.com/docs/guides/prompt-caching',
        retention_observation_state: 'observed',
        retention_observation_reason: 'provider returned cached input tokens for this session',
        observation_sample_source: 'dominant_model',
        observation_model_name: 'gpt-4.1',
        observed_calls: 2,
        observed_input_tokens: 6000,
        observed_cached_tokens: 1200,
        observed_cache_hit_rate: 0.2,
      },
    });

    expect(screen.getByText('contextHealth.title')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.compaction.title')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.title')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.cache.title')).toBeInTheDocument();
    expect(screen.getByText('4.2k')).toBeInTheDocument();
    expect(screen.getByText('8.2k')).toBeInTheDocument();
    expect(screen.getByText('1.0k')).toBeInTheDocument();
    expect(screen.getByText('25.0%')).toBeInTheDocument();
    expect(screen.getByText('16.6%')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.cache.observationStates.observed')).toBeInTheDocument();
    expect(screen.getByText(/contextHealth\.cache\.sampleSources\.dominantModel/)).toBeInTheDocument();
    expect(screen.getByText(/gpt-4\.1: 2 \/ 6\.0k \/ 1\.2k \/ 20\.0%/)).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.recentRestoreBlocks')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.signals.restoreBlocked')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.backoffActive')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.backoffReasonLabels.highRestoreCostRatio')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.cache.strategies.coldWatch')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.restoreReasons.archiveRestoreRangeRequired')).toBeInTheDocument();
    expect(screen.getByText(/contextHealth\.pruning\.contentFeatures\.jsonKeys: status, errors/)).toBeInTheDocument();
    expect(screen.getByText(/contextHealth\.pruning\.restoreHintReasons\.errorKeyword/)).toBeInTheDocument();
    expect(screen.getByText(/contextHealth\.pruning\.restoreHintReasons\.codeBlock/)).toBeInTheDocument();
    expect(screen.getByText('.context/chat/compacted/result.txt:1-200')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.copyRestoreArg')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.restoreRange')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.restoreRequested')).toBeInTheDocument();
    expect(screen.getByText('contextHealth.pruning.restoreAllowed')).toBeInTheDocument();
    expect(screen.getByText('33.3%')).toBeInTheDocument();
    expect(screen.getByText('quota_exceeded: 1')).toBeInTheDocument();
    expect(screen.getByText('archive_count_budget: 2')).toBeInTheDocument();
    expect(screen.getByText('offload_bytes_budget: 3')).toBeInTheDocument();
    expect(screen.getAllByText('contextHealth.status.warning')).not.toHaveLength(0);
  });

  it('submits active-session restore ranges as typed actions', async () => {
    const sendMessage = vi.fn<typeof originalSendMessage>().mockResolvedValue(undefined);
    useChatStore.setState({ chatId: 'session-1', sendMessage });

    renderPanel({
      status: 'warning',
      compaction: {
        status: 'inactive',
        active: false,
        count: 0,
        tokens_saved: 0,
        net_tokens_saved: 0,
        efficiency: 0,
        refetch_count: 0,
        refetch_ratio: 0,
        dedup_tokens_saved: 0,
        integrity_skipped: 0,
        summary_persisted: false,
        last_compacted_at: null,
      },
      pruning: {
        status: 'warning',
        active: true,
        archived: 1,
        soft_trimmed: 0,
        offload_failed: 0,
        archive_written_count: 1,
        archive_reused_count: 0,
        archive_bytes_written: 100,
        archive_bytes_reused: 0,
        deferred_count: 0,
        deferred_reasons: {},
        archive_deferred_count: 0,
        archive_deferred_reasons: {},
        archive_deferred_soft_trimmed_count: 0,
        archive_deferred_soft_trimmed_reasons: {},
        archive_refetch_count: 0,
        archive_refetch_tokens: 0,
        archive_restore_requested_count: 1,
        archive_restore_allowed_count: 0,
        archive_restore_blocked_count: 1,
        archive_restore_blocked_ratio: 1,
        archive_restore_result_count: 0,
        archive_restore_result_tokens: 0,
        archive_restore_result_lines: 0,
        archive_restore_result_bytes: 0,
        pruning_restore_cost_ratio: 0,
        pruning_restore_roi_ratio: 0.9,
        archive_restore_block_events: [
          {
            timestamp: '2026-05-19T00:00:00+00:00',
            reason: 'archive_restore_range_required',
            estimated_tokens: 2500,
            archive_path: '.context/session-1/compacted/result.txt',
            message: 'Full archive restore blocked.',
            suggested_action: 'Read a targeted line range from chunk_restore_args.',
            reason_label_key: 'archive_restore_range_required',
            severity: 'warning',
            primary_restore_arg: '.context/session-1/compacted/result.txt:1-200',
            recommended_ranges: [],
            restore_range_hints: [],
            content_features: [],
            guidance_source: 'restore_map',
            fallback_reason: '',
          },
        ],
        offload_failure_kinds: {},
        original_tokens: 2500,
        tokens_saved: 1000,
        net_tokens_saved: 900,
        refetch_ratio: 0,
        backoff_applied: false,
        backoff_reasons: {},
        effective_soft_trim_ratio: 0,
        effective_hard_clear_ratio: 0,
        effective_min_prunable_tokens: 0,
        archive_summary_queued_count: 0,
        archive_summary_succeeded_count: 0,
        archive_summary_failed_count: 0,
        archive_summary_skipped_count: 0,
        archive_summary_skipped_reasons: {},
      },
      cache: {
        status: 'inactive',
        active: false,
        calls: 0,
        input_tokens: 0,
        cached_tokens: 0,
        cache_hit_rate: 0,
        model_family: 'unknown',
        retention_mode: 'unknown',
        ttl_seconds: 0,
        policy_reason: '',
        policy_source_url: '',
        retention_observation_state: 'insufficient_data',
        retention_observation_reason: '',
        observation_sample_source: 'session_aggregate',
        observation_model_name: '',
        observed_calls: 0,
        observed_input_tokens: 0,
        observed_cached_tokens: 0,
        observed_cache_hit_rate: 0,
      },
    });

    fireEvent.click(screen.getByText('contextHealth.pruning.restoreRange'));

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith('contextHealth.pruning.restorePrompt', undefined, undefined, undefined, [
        { type: 'archive_restore', restoreArg: '.context/session-1/compacted/result.txt:1-200' },
      ]);
    });
  });
});
