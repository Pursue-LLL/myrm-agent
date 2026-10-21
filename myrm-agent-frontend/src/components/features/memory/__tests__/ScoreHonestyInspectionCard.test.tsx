/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 142 RetrievalScoreHonestyRawVsRanking:
 * 1. Default render of HUD telemetry bar, threshold sliders, and candidates list.
 * 2. Evaluating candidates successfully with mock service response.
 * 3. Toggling strict mode dual threshold switch.
 * 4. Changing slider thresholds and updating scores.
 * 5. Expanding detailed white-box ScoreBreakdown factors.
 * 6. Graceful client-side fallback on service rejection.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ScoreHonestyInspectionCard } from '../command-center/ScoreHonestyInspectionCard';

const { mockEvaluateCandidates, mockGetStats } = vi.hoisted(() => ({
  mockEvaluateCandidates: vi.fn(),
  mockGetStats: vi.fn(),
}));

vi.mock('@/services/memory/scoreHonesty', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    scoreHonestyService: {
      evaluateCandidates: mockEvaluateCandidates,
      filterCandidates: vi.fn(),
      getStats: mockGetStats,
      checkHealth: vi.fn(),
    },
  };
});

describe('ScoreHonestyInspectionCard (Item 142 P1)', () => {
  const sampleStats = {
    total_candidates: 2,
    admitted_count: 1,
    rejected_count: 1,
    raw_admitted_count: 1,
    ranking_admitted_count: 2,
    both_passed_count: 1,
    divergence_count: 1,
    divergence_rate: 0.5,
    mean_raw_similarity: 0.6,
    mean_ranking_score: 0.55,
  };

  const sampleEvaluated = [
    {
      id: 'cand-001',
      content: '用户在 Postgres 数据库中对大表查询开启并行扫描优化',
      raw_similarity: 0.88,
      ranking_score: 0.85,
      breakdown: {
        raw_similarity: 0.88,
        recency_factor: 1.15,
        importance_boost: 1.1,
        mmr_penalty: 0.05,
        rrf_score: 0.02,
        final_ranking_score: 0.85,
        explanation: 'raw=0.880 * recency=1.15 => ranking=0.850',
      },
      metadata: {},
      verdict: {
        passed_raw: true,
        passed_ranking: true,
        admitted: true,
        rejection_stage: 'none',
        rejection_reason: null,
      },
    },
    {
      id: 'cand-002',
      content: '昨日临时调试日志：Qdrant 向量维度采样飞行前自愈通过',
      raw_similarity: 0.35,
      ranking_score: 0.75,
      breakdown: {
        raw_similarity: 0.35,
        recency_factor: 1.85,
        importance_boost: 1.2,
        mmr_penalty: 0.0,
        rrf_score: 0.03,
        final_ranking_score: 0.75,
        explanation: 'raw=0.350 * recency=1.85 => ranking=0.750',
      },
      metadata: {},
      verdict: {
        passed_raw: false,
        passed_ranking: true,
        admitted: false,
        rejection_stage: 'raw_below_threshold',
        rejection_reason: 'Candidate raw similarity 0.350 below floor 0.500',
      },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockEvaluateCandidates.mockResolvedValue({
      evaluated: sampleEvaluated,
      stats: sampleStats,
    });
    mockGetStats.mockResolvedValue(sampleStats);
  });

  it('renders card title, threshold controls, and HUD telemetry', async () => {
    render(<ScoreHonestyInspectionCard />);

    expect(screen.getByText('检索评分诚实性检验看板')).toBeInTheDocument();
    expect(screen.getByText('Raw 向量门禁地板')).toBeInTheDocument();
    expect(screen.getByText('Ranking 复合门禁地板')).toBeInTheDocument();
    expect(screen.getByText('双门禁严格模式')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('总评估样本')).toBeInTheDocument();
      expect(screen.getByText('准入采纳')).toBeInTheDocument();
      expect(screen.getByText(/拒绝: raw_below_threshold/)).toBeInTheDocument();
      expect(screen.getByText('Raw/Ranking 分歧')).toBeInTheDocument();
    });
  });

  it('expands white-box breakdown when chevron is clicked', async () => {
    render(<ScoreHonestyInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText('cand-001')).toBeInTheDocument();
    });

    const expandBtn = screen.getByLabelText('展开 cand-001 评分因子');
    fireEvent.click(expandBtn);

    expect(screen.getByText('白盒归因因子明细：')).toBeInTheDocument();
    expect(screen.getByText(/Recency: ×1.15/)).toBeInTheDocument();
    expect(screen.getByText(/raw=0.880 \* recency=1.15/)).toBeInTheDocument();
  });

  it('toggles strict mode switch and triggers evaluation', async () => {
    render(<ScoreHonestyInspectionCard />);

    const switchBtn = screen.getByRole('switch');
    expect(switchBtn).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(switchBtn);
    expect(switchBtn).toHaveAttribute('aria-checked', 'false');

    await waitFor(() => {
      expect(mockEvaluateCandidates).toHaveBeenCalledTimes(2);
      expect(mockEvaluateCandidates).toHaveBeenLastCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ strict_mode: false }),
        })
      );
    });
  });

  it('updates raw threshold slider and triggers evaluation', async () => {
    render(<ScoreHonestyInspectionCard />);

    const slider = screen.getByLabelText('Raw 向量相似度阈值');
    fireEvent.change(slider, { target: { value: '0.7' } });

    await waitFor(() => {
      expect(mockEvaluateCandidates).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({ raw_similarity_threshold: 0.7 }),
        })
      );
    });
  });

  it('falls back gracefully to offline simulation when API errors', async () => {
    mockEvaluateCandidates.mockRejectedValueOnce(new Error('Network Offline'));

    render(<ScoreHonestyInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText('总评估样本')).toBeInTheDocument();
      // Verifies cards still render with fallback simulation
      expect(screen.getByText('cand-001')).toBeInTheDocument();
    });
  });
});
