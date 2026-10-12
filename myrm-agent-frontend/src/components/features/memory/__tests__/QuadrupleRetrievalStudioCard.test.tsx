/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(fetchQuadrupleRetrievalStats, executeQuadrupleSearch)
 * ../command-center/QuadrupleRetrievalStudioCard::QuadrupleRetrievalStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Goal-Driven Quadruple Retrieval & Reasoner Studio Card (Item 127 P1):
 * 1. Default render of HUD metric bar, goal parser console, recall matrix, and reranked hits
 * 2. Execution of custom user query via search button
 * 3. Quick preset query switching and immediate recall execution
 * 4. Collapsible reasoner audit rationale expansion
 * 5. Refreshing engine telemetry stats via HUD button
 * 6. Graceful fallback on API error
 *
 * [POS]
 * Unit tests for Item 127.
 * Strict typing applied: Zero `any` types. Single file < 250 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { QuadrupleRetrievalStudioCard } from '../command-center/QuadrupleRetrievalStudioCard';
import {
  FALLBACK_RETRIEVAL_STATS,
  FALLBACK_SEARCH_RESPONSE,
} from '../command-center/quadrupleRetrievalFallbacks';

const { mockFetchStats, mockExecuteSearch } = vi.hoisted(() => ({
  mockFetchStats: vi.fn(),
  mockExecuteSearch: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    fetchQuadrupleRetrievalStats: mockFetchStats,
    executeQuadrupleSearch: mockExecuteSearch,
  };
});

describe('QuadrupleRetrievalStudioCard (Item 127 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchStats.mockResolvedValue(FALLBACK_RETRIEVAL_STATS);
    mockExecuteSearch.mockResolvedValue(FALLBACK_SEARCH_RESPONSE);
  });

  it('renders default HUD metrics, goal deconstruction, recall matrix, and ranked hits', async () => {
    render(<QuadrupleRetrievalStudioCard />);

    // 1. Header & HUD verification
    expect(
      screen.getByText('四路并行检索与推理重排工作台')
    ).toBeInTheDocument();
    expect(screen.getByText(/Indexed: 142/)).toBeInTheDocument();
    expect(screen.getByText(/Channels: 4 \/ 4 Active/)).toBeInTheDocument();

    // 2. TaskGoalParser verification
    expect(screen.getByText('TaskGoalParser 解构分析')).toBeInTheDocument();
    expect(screen.getByText(/意图: technical_standard/)).toBeInTheDocument();
    expect(screen.getByText('架构红线')).toBeInTheDocument();

    // 3. 4-way recall matrix verification
    expect(screen.getByText('四路并行召回 & 多通道融合矩阵')).toBeInTheDocument();
    expect(screen.getByText(/Graph 拓扑通道/)).toBeInTheDocument();
    expect(screen.getByText(/Vector 稠密通道/)).toBeInTheDocument();
    expect(screen.getByText(/Lexical 词法通道/)).toBeInTheDocument();
    expect(screen.getByText(/Metadata 过滤通道/)).toBeInTheDocument();

    // 4. Reasoner reranked hits
    expect(screen.getByText(/#1/)).toBeInTheDocument();
    expect(screen.getByText('mem_arch_001')).toBeInTheDocument();
    expect(screen.getByText('意图强化 (Boost)')).toBeInTheDocument();
  });

  it('allows user to execute custom query via search form', async () => {
    render(<QuadrupleRetrievalStudioCard />);

    const searchInput = screen.getByPlaceholderText(
      /输入自然语言查询（如：项目单文件行数限制和 any 类型红线）.../
    );
    fireEvent.change(searchInput, { target: { value: '测试检索最新架构规范' } });

    const searchBtn = screen.getByRole('button', { name: '执行四路并行检索' });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockExecuteSearch).toHaveBeenCalledWith({
        query: '测试检索最新架构规范',
        top_k: 4,
      });
    });
  });

  it('switches query and triggers search when clicking preset query button', async () => {
    render(<QuadrupleRetrievalStudioCard />);

    const presetBtn = screen.getByRole('button', {
      name: '载入预设查询: 过时方案衰减惩罚',
    });
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(mockExecuteSearch).toHaveBeenCalledWith({
        query: '检索关于集中式全量检索 router proxy 与废弃网关的记忆',
        top_k: 4,
      });
    });
  });

  it('toggles collapsible reasoner audit rationale', async () => {
    render(<QuadrupleRetrievalStudioCard />);

    const toggleButtons = screen.getAllByRole('button', {
      name: /展开 Reasoner 审计推导原因/,
    });
    expect(toggleButtons.length).toBeGreaterThan(0);

    // Click the first one to expand rationale
    fireEvent.click(toggleButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'Reasoner 审计理由说明' })).toBeInTheDocument();
      expect(screen.getByText(/审计归因:/)).toBeInTheDocument();
    });

    // Click again to collapse
    const collapseButton = screen.getByRole('button', {
      name: /收起 Reasoner 审计推导原因/,
    });
    fireEvent.click(collapseButton);

    await waitFor(() => {
      expect(screen.queryByRole('region', { name: 'Reasoner 审计理由说明' })).not.toBeInTheDocument();
    });
  });

  it('refreshes telemetry stats when clicking refresh in HUD', async () => {
    render(<QuadrupleRetrievalStudioCard />);

    const refreshBtn = screen.getByRole('button', {
      name: '刷新四路检索引擎指标',
    });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockFetchStats).toHaveBeenCalled();
    });
  });

  it('handles API error gracefully by rendering fallback data and error message', async () => {
    mockExecuteSearch.mockRejectedValueOnce(new Error('Network connection timeout'));

    render(<QuadrupleRetrievalStudioCard />);

    const searchBtn = screen.getByRole('button', { name: '执行四路并行检索' });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(screen.getByText('Network connection timeout')).toBeInTheDocument();
    });
  });
});
