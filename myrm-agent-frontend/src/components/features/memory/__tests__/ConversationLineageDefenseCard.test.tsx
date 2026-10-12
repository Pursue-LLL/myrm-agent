/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/conversationLineageDefense::searchWithLineageDefense, getLineageDefenseStats
 * ../command-center/ConversationLineageDefenseCard::ConversationLineageDefenseCard
 *
 * [OUTPUT]
 * Test suite verifying source-aware demotion, lineage generational deduplication,
 * asymmetric progressive window hydration, and token footprint savings.
 *
 * [POS]
 * Unit test for Item 97 (LineageDedupRecallBlindnessDefenseAndAutomationDemotionSuite).
 * Strict typing applied: No `any` types allowed. File lines < 400.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationLineageDefenseCard } from '../command-center/ConversationLineageDefenseCard';
import type {
  LineageDefenseSearchResponseDTO,
  LineageDefenseStatsDTO,
} from '@/services/memory/conversationLineageDefense';

const { mockSearchWithLineageDefense, mockGetLineageDefenseStats } = vi.hoisted(() => ({
  mockSearchWithLineageDefense: vi.fn(),
  mockGetLineageDefenseStats: vi.fn(),
}));

vi.mock('@/services/memory/conversationLineageDefense', () => ({
  searchWithLineageDefense: mockSearchWithLineageDefense,
  getLineageDefenseStats: mockGetLineageDefenseStats,
}));

describe('ConversationLineageDefenseCard', () => {
  const sampleSearchResponse: LineageDefenseSearchResponseDTO = {
    query: 'authentication token validation',
    hits: [
      {
        session_id: 'chat_auth_refactor_v2',
        lineage_root_id: 'root_auth_refactor',
        title: 'Authentication Middleware Implementation Compaction v2',
        source_kind: 'interactive',
        detail_level: 'expanded_window',
        content_snippet: 'Dependency get_current_user implemented with full 401 handling.',
        window_messages: [
          'SUMMARY: Previous round decided on 24h HMAC tokens.',
          "USER: Let's write the FastAPI dependency and unit tests.",
          'AGENT: Dependency get_current_user implemented with full 401 handling.',
        ],
        token_estimate: 42,
        is_demoted: false,
        is_lineage_primary: true,
        collapsed_generations_count: 1,
        collapsed_session_ids: ['chat_auth_refactor_v1'],
      },
      {
        session_id: 'cron_hourly_db_vacuum',
        lineage_root_id: 'cron_hourly_db_vacuum',
        title: 'Scheduled Database Vacuum & Health Check',
        source_kind: 'cron',
        detail_level: 'compact_card',
        content_snippet: 'Processed 128 SQLite memory tables without error.',
        window_messages: [],
        token_estimate: 14,
        is_demoted: true,
        is_lineage_primary: true,
        collapsed_generations_count: 0,
        collapsed_session_ids: [],
      },
    ],
    audit_report: {
      total_candidates: 4,
      retained_hits_count: 2,
      hidden_internal_count: 1,
      demoted_cron_count: 1,
      collapsed_lineage_count: 1,
      interactive_top1_ratio: 1.0,
      estimated_tokens_saved: 480,
      token_saving_percent: 68.5,
    },
  };

  const sampleStats: LineageDefenseStatsDTO = {
    total_inspected_sessions: 4,
    interactive_sessions_count: 2,
    cron_sessions_count: 1,
    internal_workers_count: 1,
    average_token_savings_percent: 68.5,
    recall_blindness_defense_active: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchWithLineageDefense.mockResolvedValue(sampleSearchResponse);
    mockGetLineageDefenseStats.mockResolvedValue(sampleStats);
  });

  it('renders HUD statistics and default progressive search hits correctly', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(
        screen.getByText('会话血统代际去重与自动化降权套件')
      ).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-interactive-ratio')).toHaveTextContent('100%');
    expect(screen.getByTestId('hud-cron-demoted')).toHaveTextContent('1 项');
    expect(screen.getByTestId('hud-lineage-collapsed')).toHaveTextContent('1 代');
    expect(screen.getByTestId('hud-token-savings')).toHaveTextContent('68.5%');

    // Hits list rendering
    expect(screen.getByTestId('hit-item-chat_auth_refactor_v2')).toBeInTheDocument();
    expect(screen.getByTestId('hit-item-cron_hourly_db_vacuum')).toBeInTheDocument();
  });

  it('submits test search query and updates results', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(screen.getByTestId('lineage-search-form')).toBeInTheDocument();
    });

    const queryInput = screen.getByLabelText(/会话检索测试语句/);
    fireEvent.change(queryInput, { target: { value: 'custom sqlite optimization' } });

    const submitBtn = screen.getByTestId('btn-execute-defense-search');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockSearchWithLineageDefense).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'custom sqlite optimization',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/防盲区检索完成/)).toBeInTheDocument();
    });
  });

  it('toggles include internal workers checkbox and adjusts cron penalty multiplier', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(screen.getByLabelText(/包含内部 Worker 会话/)).toBeInTheDocument();
    });

    const checkbox = screen.getByLabelText(/包含内部 Worker 会话/);
    fireEvent.click(checkbox);

    const selectMultiplier = screen.getByLabelText(/选择 Cron 降权系数/);
    fireEvent.change(selectMultiplier, { target: { value: '0.3' } });

    const submitBtn = screen.getByTestId('btn-execute-defense-search');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockSearchWithLineageDefense).toHaveBeenCalledWith(
        expect.objectContaining({
          include_internal: true,
          cron_weight_multiplier: 0.3,
        })
      );
    });
  });

  it('switches to lineage dedup tab and renders lineage root cards', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-lineage-dedup')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-lineage-dedup'));

    await waitFor(() => {
      expect(screen.getByTestId('conversation-lineage-dedup-view')).toBeInTheDocument();
    });

    expect(screen.getByTestId('lineage-card-chat_auth_refactor_v2')).toBeInTheDocument();
    expect(screen.getByTestId('lineage-card-cron_hourly_db_vacuum')).toBeInTheDocument();
    expect(screen.getByText(/折叠 1 个祖先代际/)).toBeInTheDocument();
  });

  it('expands collapsed ancestor generation slices when clicking toggle button', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-lineage-dedup')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-lineage-dedup'));

    await waitFor(() => {
      expect(
        screen.getByTestId('btn-toggle-collapsed-chat_auth_refactor_v2')
      ).toBeInTheDocument();
    });

    const toggleBtn = screen.getByTestId('btn-toggle-collapsed-chat_auth_refactor_v2');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(
        screen.getByTestId('collapsed-panel-chat_auth_refactor_v2')
      ).toBeInTheDocument();
    });

    expect(screen.getByText(/chat_auth_refactor_v1/)).toBeInTheDocument();
  });

  it('refreshes defense status when clicking the refresh button', async () => {
    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockSearchWithLineageDefense).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully degrades to fallback state on API failure', async () => {
    mockSearchWithLineageDefense.mockRejectedValue(new Error('Network error'));

    render(<ConversationLineageDefenseCard />);

    await waitFor(() => {
      expect(
        screen.getByText('会话血统代际去重与自动化降权套件')
      ).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-interactive-ratio')).toHaveTextContent('—');
    expect(screen.getByTestId('hud-cron-demoted')).toHaveTextContent('—');
  });
});
