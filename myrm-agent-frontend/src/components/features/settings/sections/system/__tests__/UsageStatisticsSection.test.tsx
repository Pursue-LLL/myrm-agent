/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getDailyUsage,
  getGlobalActivityPatterns,
  getPromptCacheRadar,
  getSessionUsage,
  getTopSessions,
  getUsageStatistics,
  type DailyUsageResponse,
  type GlobalActivityPatterns,
  type PromptCacheRadarData,
  type TopSession,
  type UsageStats,
} from '@/services/statistics';
import { getWikiEvidenceSummary, type WikiEvidenceSummary } from '@/services/wiki/evidenceMetrics';

import UsageStatisticsSection from '../UsageStatisticsSection';
import { downloadUsageCsv } from '../usageExport';

// 翻译函数必须是稳定引用：每次渲染都新建会让依赖它的 hook 反复重建。
const { translate } = vi.hoisted(() => ({ translate: (key: string) => key }));

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
  useLocale: () => 'en',
}));

vi.mock('@/services/statistics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/statistics')>()),
  getUsageStatistics: vi.fn(),
  getDailyUsage: vi.fn(),
  getSessionUsage: vi.fn(),
  getGlobalActivityPatterns: vi.fn(),
  getTopSessions: vi.fn(),
  getPromptCacheRadar: vi.fn(),
}));

vi.mock('@/services/wiki/evidenceMetrics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/wiki/evidenceMetrics')>()),
  getWikiEvidenceSummary: vi.fn(),
}));

vi.mock('../usageExport', () => ({ downloadUsageCsv: vi.fn() }));
vi.mock('../BudgetPolicySection', () => ({ default: () => null }));
vi.mock('../ChannelBudgetSection', () => ({ default: () => null }));
vi.mock('../AgentCommerceBudgetSection', () => ({ default: () => null }));
vi.mock('../../knowledge/MemoryGuardianCard', () => ({ default: () => null }));
vi.mock('../AgentUsageCard', () => ({ default: () => null }));
vi.mock('../RoutingAnalyticsPanel', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../RoutingAnalyticsPanel')>()),
  default: () => <div data-testid="routing-panel" />,
}));
vi.mock('../SessionAnalyticsDialog', () => ({
  default: ({ sessionId, onClose }: { sessionId: string; onClose: () => void }) => (
    <div data-testid="session-dialog">
      <span>{sessionId}</span>
      <button onClick={onClose}>close-dialog</button>
    </div>
  ),
}));
vi.mock('../UsageStatisticsCharts', () => ({
  StatCard: ({ label, value }: { label: string; value: string }) => (
    <div data-testid="stat-card">{`${label}=${value}`}</div>
  ),
  SessionTable: ({ onSelectSession }: { onSelectSession: (id: string) => void }) => (
    <button onClick={() => onSelectSession('s-42')}>open-session</button>
  ),
  DailyChart: () => null,
  ModelBreakdown: () => null,
  PrivacyRoutePanel: () => null,
  WeekDistributionChart: () => null,
  ActivityDailyChart: () => null,
  HourDistributionChart: () => null,
}));

const STATS: UsageStats = {
  calls: 12,
  inputTokens: 1000,
  outputTokens: 500,
  cachedTokens: 200,
  reasoningTokens: 50,
  citationTokens: 0,
  totalTokens: 1500,
  costUsd: 0.5,
  cacheHitRate: 0.2,
  modelBreakdown: {},
};
const DAILY: DailyUsageResponse = { days: 30, start: '2026-01-01', end: '2026-01-30', daily: [] };
const ACTIVITY: GlobalActivityPatterns = {
  timezone: 'UTC',
  daily_activities: [],
  by_day_of_week: {},
  by_hour: {},
  active_days: 3,
  max_streak: 2,
  busiest_day_of_week: 1,
  busiest_hour: 14,
};
const TOP_SESSIONS: TopSession[] = [
  {
    session_id: 'abcdef1234567890',
    metric_value: 5,
    metric_type: 'duration',
    started_at: 1_700_000_000,
    duration_ms: 180_000,
    message_count: 4,
    total_tokens: 2500,
    tool_calls: 7,
  },
];
const RADAR: PromptCacheRadarData = {
  days: 30,
  sessions_tracked: 2,
  total_prompt_tokens: 3000,
  fresh_input_tokens: 1000,
  total_cache_read_tokens: 2000,
  total_completion_tokens: 500,
  prompt_cache_hit_ratio: 0.66,
  estimated_savings_usd: 0.0123,
};
const WIKI: WikiEvidenceSummary = {
  days: 30,
  retention_days: 90,
  total_events: 10,
  evidence_surface_count: 4,
  snippet_open_count: 3,
  dropped_event_count: 0,
  snippet_expansion_rate: 0.5,
  deep_verification_count: 2,
  deep_verification_rate: 0.25,
  quick_bounce_count: 1,
  quick_bounce_rate: 0.1,
  quality_outcome_negative_count: 0,
  quality_outcome_negative_rate: 0,
  query_attempt_count: 5,
  query_success_count: 4,
  query_success_rate: 0.8,
  query_count: 6,
  requery_count: 1,
  requery_rate: 0.2,
  verification_dwell_avg_ms: 4000,
  verification_dwell_sample_count: 3,
  snippet_open_by_surface: { chat: 2, settings: 1 },
  snippet_open_by_level: { L0: 1, L1: 1, L2: 1 },
  quality_outcome_negative_by_surface: { chat: 0, settings: 0 },
};

beforeEach(() => {
  vi.mocked(getUsageStatistics).mockResolvedValue(STATS);
  vi.mocked(getDailyUsage).mockResolvedValue(DAILY);
  vi.mocked(getSessionUsage).mockResolvedValue({ sessions: [] });
  vi.mocked(getGlobalActivityPatterns).mockResolvedValue(ACTIVITY);
  vi.mocked(getTopSessions).mockResolvedValue(TOP_SESSIONS);
  vi.mocked(getWikiEvidenceSummary).mockResolvedValue(WIKI);
  vi.mocked(getPromptCacheRadar).mockResolvedValue(RADAR);
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('UsageStatisticsSection', () => {
  it('loads every statistic for the default 30-day window', async () => {
    render(<UsageStatisticsSection />);

    expect(await screen.findByText('wikiEvidenceTitle')).toBeInTheDocument();
    expect(screen.getAllByTestId('stat-card')[0]).toHaveTextContent('totalTokens=');
    expect(getGlobalActivityPatterns).toHaveBeenCalledWith(30);
    expect(getTopSessions).toHaveBeenCalledWith('duration', 10, 30);
    expect(getWikiEvidenceSummary).toHaveBeenCalledWith(30);
    expect(getPromptCacheRadar).toHaveBeenCalledWith(30);
  });

  it('shows the prompt cache radar only when sessions were tracked', async () => {
    const { unmount } = render(<UsageStatisticsSection />);
    expect(await screen.findByText('cacheRadarTitle')).toBeInTheDocument();
    unmount();

    vi.mocked(getPromptCacheRadar).mockResolvedValue({ ...RADAR, sessions_tracked: 0 });
    render(<UsageStatisticsSection />);
    await screen.findByText('wikiEvidenceTitle');
    expect(screen.queryByText('cacheRadarTitle')).not.toBeInTheDocument();
  });

  it('hides the wiki evidence section when its summary fails to load', async () => {
    vi.mocked(getWikiEvidenceSummary).mockRejectedValue(new Error('unavailable'));

    render(<UsageStatisticsSection />);

    expect(await screen.findByText('cacheRadarTitle')).toBeInTheDocument();
    expect(screen.queryByText('wikiEvidenceTitle')).not.toBeInTheDocument();
  });

  it('reloads every window-scoped statistic for the chosen time range', async () => {
    render(<UsageStatisticsSection />);

    fireEvent.click(await screen.findByText('timeRange7Days'));

    await waitFor(() => {
      expect(getGlobalActivityPatterns).toHaveBeenLastCalledWith(7);
      expect(getTopSessions).toHaveBeenLastCalledWith('duration', 10, 7);
      expect(getWikiEvidenceSummary).toHaveBeenLastCalledWith(7);
      expect(getPromptCacheRadar).toHaveBeenLastCalledWith(7);
    });
  });

  it('reloads the top sessions for the chosen metric', async () => {
    render(<UsageStatisticsSection />);

    fireEvent.click(await screen.findByText('metricTokens'));

    await waitFor(() => expect(getTopSessions).toHaveBeenLastCalledWith('tokens', 10, 30));
  });

  it('shows the empty states when there is no activity and no top sessions', async () => {
    vi.mocked(getGlobalActivityPatterns).mockResolvedValue({ ...ACTIVITY, active_days: 0 });
    vi.mocked(getTopSessions).mockResolvedValue([]);

    render(<UsageStatisticsSection />);

    expect(await screen.findByText('noActivityTitle')).toBeInTheDocument();
    expect(screen.getByText('noTopSessionsTitle')).toBeInTheDocument();
    expect(screen.queryByText('timeRange7Days')).not.toBeInTheDocument();
  });

  it('exports the loaded statistics as CSV', async () => {
    render(<UsageStatisticsSection />);

    fireEvent.click(await screen.findByTestId('export-usage-csv-btn'));

    expect(downloadUsageCsv).toHaveBeenCalledWith(STATS, DAILY.daily);
  });

  it('opens and closes the session analytics dialog', async () => {
    render(<UsageStatisticsSection />);

    fireEvent.click(await screen.findByText('open-session'));
    expect(screen.getByTestId('session-dialog')).toHaveTextContent('s-42');

    fireEvent.click(screen.getByText('close-dialog'));
    expect(screen.queryByTestId('session-dialog')).not.toBeInTheDocument();
  });

  it('shows the load error with the destructive text token and recovers on retry', async () => {
    vi.mocked(getUsageStatistics).mockRejectedValueOnce(new Error('boom'));

    const { container } = render(<UsageStatisticsSection />);

    expect(await screen.findByText('boom')).toBeInTheDocument();
    expect(container.querySelector('svg.text-destructive-text')).not.toBeNull();

    fireEvent.click(screen.getByText('retry'));

    expect(await screen.findByText('wikiEvidenceTitle')).toBeInTheDocument();
  });
});
