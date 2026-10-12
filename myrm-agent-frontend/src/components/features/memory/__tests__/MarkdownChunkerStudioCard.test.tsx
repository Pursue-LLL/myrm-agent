/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(sliceMarkdown, incrementalIndexMarkdown, hydrateChunkContext)
 * ../command-center/MarkdownChunkerStudioCard::MarkdownChunkerStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Item 132 IncrementalSlidingWindowMarkdownChunkerSuite:
 * 1. Default render of HUD telemetry, document selector, and slicing parameter inputs
 * 2. Execution of sliding window slicing and rendering chunk list with line pointers
 * 3. Execution of context hydration expanding surrounding document lines
 * 4. Simulation of incremental edit and telemetry display of token savings percentage
 * 5. Resilient fallback and alert banner on network or API failures
 *
 * [POS]
 * Unit tests for Item 132.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MarkdownChunkerStudioCard } from '../command-center/MarkdownChunkerStudioCard';
import {
  FALLBACK_HYDRATE_RESPONSE,
  FALLBACK_INCREMENTAL_RESPONSE,
  FALLBACK_SLICE_RESPONSE,
} from '../command-center/markdownChunkerFallbacks';

const {
  mockSliceMarkdown,
  mockIncrementalIndexMarkdown,
  mockHydrateChunkContext,
} = vi.hoisted(() => ({
  mockSliceMarkdown: vi.fn(),
  mockIncrementalIndexMarkdown: vi.fn(),
  mockHydrateChunkContext: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    sliceMarkdown: mockSliceMarkdown,
    incrementalIndexMarkdown: mockIncrementalIndexMarkdown,
    hydrateChunkContext: mockHydrateChunkContext,
  };
});

describe('MarkdownChunkerStudioCard (Item 132 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSliceMarkdown.mockResolvedValue(FALLBACK_SLICE_RESPONSE);
    mockIncrementalIndexMarkdown.mockResolvedValue(FALLBACK_INCREMENTAL_RESPONSE);
    mockHydrateChunkContext.mockResolvedValue(FALLBACK_HYDRATE_RESPONSE);
  });

  it('renders default HUD status bar, document selector, and slice metrics', async () => {
    render(<MarkdownChunkerStudioCard />);

    expect(
      screen.getByText('增量滑动窗口 Markdown 切片与重叠索引')
    ).toBeInTheDocument();
    expect(screen.getByText('目标源文档：')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('3 块')).toBeInTheDocument();
      expect(screen.getByText('80 tokens')).toBeInTheDocument();
      expect(screen.getByText('0.0%')).toBeInTheDocument();
    });

    expect(
      screen.getByText('滑动窗口切片可视化检视 (3 块)')
    ).toBeInTheDocument();
    expect(
      screen.getByText('内容哈希增量索引与 Token 节省遥测')
    ).toBeInTheDocument();
  });

  it('executes sliding window slicing and renders chunk list with line pointers', async () => {
    render(<MarkdownChunkerStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('3 块')).toBeInTheDocument();
    });

    expect(screen.getByText('chk_demo_01')).toBeInTheDocument();
    expect(screen.getByText('行号: L1-L7')).toBeInTheDocument();
    expect(screen.getByText('72 tokens')).toBeInTheDocument();
    expect(screen.getByText('chk_demo_02')).toBeInTheDocument();
    expect(screen.getByText('行号: L8-L22')).toBeInTheDocument();
    expect(screen.getByText('128 tokens')).toBeInTheDocument();
  });

  it('triggers context hydration expanding surrounding document lines', async () => {
    render(<MarkdownChunkerStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('chk_demo_01')).toBeInTheDocument();
    });

    const hydrateBtns = screen.getAllByRole('button', { name: /水合回溯/i });
    expect(hydrateBtns.length).toBeGreaterThan(0);
    fireEvent.click(hydrateBtns[0]);

    await waitFor(() => {
      expect(mockHydrateChunkContext).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/原文水合上下文 \(扩展前后 2 行\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/涵盖范围: L8 至 L22/i)
      ).toBeInTheDocument();
    });
  });

  it('simulates incremental edit and displays token savings telemetry', async () => {
    render(<MarkdownChunkerStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('3 块')).toBeInTheDocument();
    });

    const simulateBtn = screen.getByRole('button', {
      name: /模拟增量保存并对比/i,
    });
    fireEvent.click(simulateBtn);

    await waitFor(() => {
      expect(mockIncrementalIndexMarkdown).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getAllByText('74.8%').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('复用切片 (免计算)')).toBeInTheDocument();
      expect(screen.getByText('新增/变更切片')).toBeInTheDocument();
      expect(screen.getByText('partially_updated')).toBeInTheDocument();
    });
  });

  it('renders fallback alert banner when slicing encounters network failure', async () => {
    mockSliceMarkdown.mockRejectedValueOnce(new Error('Network error'));

    render(<MarkdownChunkerStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByText('无法连接切片服务，已载入离线模拟切片数据')
      ).toBeInTheDocument();
    });
  });
});
