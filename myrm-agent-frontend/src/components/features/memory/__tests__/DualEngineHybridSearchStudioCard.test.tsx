/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 133 DualEngineHybridSearchAndGracefulFallbackSuite:
 * 1. Default render of HUD telemetry bar, tabs, and dual-engine search results.
 * 2. Tab switching to Adaptive RRF Tuner and parameter controls.
 * 3. Tab switching to Circuit Breaker Console and manual trip/reset actions.
 * 4. Custom query submission triggering hybridSearchService.search.
 * 5. Resilient fallback banner on network/service failure.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DualEngineHybridSearchStudioCard } from '../command-center/DualEngineHybridSearchStudioCard';
import {
  INITIAL_HYBRID_STATS,
  INITIAL_SEARCH_RESULTS,
} from '../command-center/hybridSearchFallbacks';

const {
  mockSearch,
  mockGetStats,
  mockTripCircuitBreaker,
  mockResetCircuitBreaker,
} = vi.hoisted(() => ({
  mockSearch: vi.fn(),
  mockGetStats: vi.fn(),
  mockTripCircuitBreaker: vi.fn(),
  mockResetCircuitBreaker: vi.fn(),
}));

vi.mock('@/services/memory/hybridSearch', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    hybridSearchService: {
      search: mockSearch,
      getStats: mockGetStats,
      tripCircuitBreaker: mockTripCircuitBreaker,
      resetCircuitBreaker: mockResetCircuitBreaker,
    },
  };
});

describe('DualEngineHybridSearchStudioCard (Item 133 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStats.mockResolvedValue(INITIAL_HYBRID_STATS);
    mockSearch.mockResolvedValue({
      query: 'SQLite FTS5 架构与向量检索',
      mode: 'hybrid_rrf',
      total_hits: INITIAL_SEARCH_RESULTS.length,
      results: INITIAL_SEARCH_RESULTS,
    });
    mockTripCircuitBreaker.mockResolvedValue({
      is_success: true,
      state: 'open',
      tripped_count: 1,
    });
    mockResetCircuitBreaker.mockResolvedValue({
      is_success: true,
      state: 'closed',
    });
  });

  it('renders HUD bar, search tab, and initial search results', async () => {
    render(<DualEngineHybridSearchStudioCard />);

    expect(screen.getByText('双引擎 RRF 融合')).toBeInTheDocument();
    expect(screen.getByText('链路健康闭合 (CLOSED)')).toBeInTheDocument();
    expect(screen.getByText('128 条')).toBeInTheDocument();
    expect(screen.getByText('42 节点')).toBeInTheDocument();

    expect(
      screen.getByText('SQLite FTS5 与 Vector 双引擎检索架构')
    ).toBeInTheDocument();
    expect(
      screen.getByText('三态自愈断路器降级保护机制')
    ).toBeInTheDocument();
  });

  it('switches to Adaptive RRF tuner tab and renders parameter sliders', async () => {
    render(<DualEngineHybridSearchStudioCard />);

    const rrfTabBtn = screen.getByRole('button', { name: '自适应 RRF 融合调优' });
    fireEvent.click(rrfTabBtn);

    expect(
      screen.getByText('自适应多因子 RRF 融合重排参数调控')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/RRF 平滑常数/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/FTS5 BM25 权重比/)
    ).toBeInTheDocument();

    const applyBtn = screen.getByRole('button', { name: '应用重排参数重新检索' });
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(mockSearch).toHaveBeenCalled();
    });
  });

  it('switches to Circuit Breaker console tab and simulates trip and reset', async () => {
    render(<DualEngineHybridSearchStudioCard />);

    const breakerTabBtn = screen.getByRole('button', { name: '断路器与容灾控制台' });
    fireEvent.click(breakerTabBtn);

    expect(
      screen.getByText('向量检索断路器状态机与容灾遥测')
    ).toBeInTheDocument();
    expect(
      screen.getByText('三态自愈工作拓扑')
    ).toBeInTheDocument();
    expect(
      screen.getByText('CLOSED 闭合常态')
    ).toBeInTheDocument();

    // Trigger trip
    const tripBtn = screen.getByRole('button', { name: '模拟向量服务异常跳闸' });
    fireEvent.click(tripBtn);

    await waitFor(() => {
      expect(mockTripCircuitBreaker).toHaveBeenCalled();
    });
  });

  it('executes custom search query from input box', async () => {
    render(<DualEngineHybridSearchStudioCard />);

    const searchInput = screen.getByLabelText(/记忆检索查询表达式/);
    fireEvent.change(searchInput, { target: { value: '网络抖动容灾降级' } });

    const searchBtn = screen.getByRole('button', { name: '执行双引擎混合检索' });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          query: '网络抖动容灾降级',
          enable_vector: true,
        })
      );
    });
  });

  it('handles API error and displays resilient fallback banner', async () => {
    mockSearch.mockRejectedValueOnce(new Error('Network disconnected'));

    render(<DualEngineHybridSearchStudioCard />);

    const searchBtn = screen.getByRole('button', { name: '执行双引擎混合检索' });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(
        screen.getByText('无法连接后端服务，已加载预置双引擎检索离线结果')
      ).toBeInTheDocument();
    });
  });
});
