/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - @testing-library/react::render (POS: 渲染被测组件)
 * - ../ContextUsageIndicator (POS: 被测组件，由本模块导入，保证替身先于它登记)
 *
 * [OUTPUT]
 * - renderIndicator: 渲染被测组件，返回 testing-library 的渲染结果
 * - mockChatState / mockConfigState: 可变的会话 store 与配置 store 状态
 * - mockIsMobile: 可变的窄屏开关（默认桌面）
 * - mockGetSessionAnalytics: 策略健康读取替身
 * - mockHealthy / mockCriticalHealth / mockAllInactiveHealth: 三份策略健康样本
 * - resetIndicatorKit: 还原默认状态（用量环可见、有一条健康的助手消息、策略健康为 healthy、无固定文件、桌面布局）
 *
 * [POS]
 * ContextUsageIndicator 组件测试的共享底座。文案、服务与 store 都是替身；vi.mock 在本模块求值时登记。
 */
import { render } from '@testing-library/react';
import { vi } from 'vitest';
import type { ContextHealth } from '@/services/contextHealth';
import type { ContextHealthStatus } from '@/store/chat/types';
import ContextUsageIndicator from '../ContextUsageIndicator';

const translate = vi.hoisted(() => (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return `${key}:${JSON.stringify(params)}`;
  }
  return key;
});
const mockGetSessionAnalytics = vi.hoisted(() => vi.fn());
const mockGetContextPins = vi.hoisted(() => vi.fn());
const mockSetContextPins = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

vi.mock('@/services/statistics', () => ({
  getSessionAnalytics: mockGetSessionAnalytics,
}));

vi.mock('@/services/chat', () => ({
  getContextPins: mockGetContextPins,
  setContextPins: mockSetContextPins,
}));

const mockIsMobile = vi.hoisted(() => ({ value: false }));

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => mockIsMobile.value,
}));

const mockConfigState = vi.hoisted(() => ({
  showContextUsage: true,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof mockConfigState) => unknown) => selector(mockConfigState),
}));

const mockChatState = vi.hoisted(() => ({
  messages: [
    {
      role: 'assistant' as const,
      contextBudget: {
        current_tokens: 5000,
        max_context_tokens: 128000,
        usage_percent: 3.9,
        health_status: 'healthy' as ContextHealthStatus,
      },
    },
  ] as Array<{
    role: 'assistant' | 'user';
    contextBudget?: {
      current_tokens: number;
      max_context_tokens: number;
      usage_percent: number;
      health_status: ContextHealthStatus;
      messages_estimated_tokens?: number;
      bound_tools_overhead_tokens?: number;
      other_tokens?: number;
    };
  }>,
  chatId: 'test-chat-123',
  contextPinnedFiles: [] as string[],
  contextBranchesLoadError: null as string | null,
  contextPinnedFilesLoadError: null as string | null,
  setActiveSessionAnalyticsId: vi.fn(),
  setContextPinnedFiles: vi.fn(),
  setContextPinnedFilesLoadError: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selectorOrShallow: unknown) => {
      if (typeof selectorOrShallow === 'function') {
        return (selectorOrShallow as (state: typeof mockChatState) => unknown)(mockChatState);
      }
      return mockChatState;
    },
    {
      getState: () => mockChatState,
    },
  ),
}));

vi.mock('zustand/react/shallow', () => ({
  useShallow: (selector: (state: typeof mockChatState) => unknown) => selector,
}));

export const mockHealthy: ContextHealth = {
  status: 'healthy',
  compaction: {
    status: 'healthy',
    active: true,
    count: 3,
    tokens_saved: 8200,
    net_tokens_saved: 7800,
    efficiency: 0.85,
    refetch_count: 1,
    refetch_ratio: 0.05,
    dedup_tokens_saved: 400,
    integrity_skipped: 0,
    summary_persisted: true,
    last_compacted_at: '2026-05-28T10:00:00Z',
    avg_elapsed_ms: 1200,
    last_elapsed_ms: 980,
  },
  pruning: {
    status: 'inactive',
    active: false,
    archived: 0,
    soft_trimmed: 0,
    offload_failed: 0,
    archive_written_count: 0,
    archive_reused_count: 0,
    archive_bytes_written: 0,
    archive_bytes_reused: 0,
    deferred_count: 0,
    deferred_reasons: {},
    archive_deferred_count: 0,
    archive_deferred_reasons: {},
    archive_deferred_soft_trimmed_count: 0,
    archive_deferred_soft_trimmed_reasons: {},
    archive_refetch_count: 0,
    archive_refetch_tokens: 0,
    archive_restore_requested_count: 0,
    archive_restore_allowed_count: 0,
    archive_restore_blocked_count: 0,
    archive_restore_blocked_ratio: 0,
    archive_restore_result_count: 0,
    archive_restore_result_tokens: 0,
    archive_restore_result_lines: 0,
    archive_restore_result_bytes: 0,
    pruning_restore_cost_ratio: 0,
    pruning_restore_roi_ratio: 0,
    archive_restore_block_events: [],
    offload_failure_kinds: {},
    original_tokens: 0,
    tokens_saved: 0,
    net_tokens_saved: 0,
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
    status: 'healthy',
    active: true,
    calls: 15,
    input_tokens: 50000,
    cached_tokens: 36000,
    cache_hit_rate: 0.72,
    model_family: 'claude',
    retention_mode: 'observed',
    ttl_seconds: 300,
    policy_reason: 'model_default',
    policy_source_url: '',
    retention_observation_state: 'observed',
    retention_observation_reason: 'sufficient_calls',
    observation_sample_source: 'dominant_model',
    observation_model_name: 'claude-sonnet-4-20250514',
    observed_calls: 15,
    observed_input_tokens: 50000,
    observed_cached_tokens: 36000,
    observed_cache_hit_rate: 0.72,
  },
};

export const mockCriticalHealth: ContextHealth = {
  ...mockHealthy,
  status: 'critical',
  pruning: {
    ...mockHealthy.pruning,
    active: true,
    archived: 5,
    archive_restore_blocked_count: 3,
  },
};

export const mockAllInactiveHealth: ContextHealth = {
  ...mockHealthy,
  status: 'inactive',
  compaction: { ...mockHealthy.compaction, active: false },
  pruning: { ...mockHealthy.pruning, active: false },
  cache: { ...mockHealthy.cache, active: false },
};

export function resetIndicatorKit(): void {
  vi.clearAllMocks();
  mockConfigState.showContextUsage = true;
  mockIsMobile.value = false;
  mockChatState.messages = [
    {
      role: 'assistant' as const,
      contextBudget: {
        current_tokens: 5000,
        max_context_tokens: 128000,
        usage_percent: 3.9,
        health_status: 'healthy' as const,
      },
    },
  ];
  mockGetSessionAnalytics.mockResolvedValue({ context_health: mockHealthy });
  mockGetContextPins.mockResolvedValue({ files: [] });
  mockSetContextPins.mockResolvedValue({ files: [] });
}

export function renderIndicator() {
  return render(<ContextUsageIndicator />);
}

export { mockChatState, mockConfigState, mockGetSessionAnalytics, mockIsMobile };
