/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(fetchCorrectionCandidates, fetchCorrectionHistory, fetchCorrectionStatus, processLiveCorrection, resetCorrectionPool)
 * ../command-center/LiveCorrectionStudioCard::LiveCorrectionStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Natural Language Memory Feedback & Live Correction Studio Card (Item 128 P0):
 * 1. Default render of HUD status bar, input form, and candidate memory nodes
 * 2. Execution of live correction mutation with natural language receipt rendering
 * 3. Quick sample chip clicking to fill utterance
 * 4. Resetting testing candidate pool via HUD button
 * 5. Error handling and alert banner on unrecognized utterances
 *
 * [POS]
 * Unit tests for Item 128.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveCorrectionStudioCard } from '../command-center/LiveCorrectionStudioCard';
import {
  FALLBACK_CANDIDATES,
  FALLBACK_HISTORY,
  FALLBACK_RECEIPT,
  FALLBACK_STATUS,
} from '../command-center/liveCorrectionFallbacks';

const {
  mockFetchCandidates,
  mockFetchHistory,
  mockFetchStatus,
  mockProcessCorrection,
  mockResetPool,
} = vi.hoisted(() => ({
  mockFetchCandidates: vi.fn(),
  mockFetchHistory: vi.fn(),
  mockFetchStatus: vi.fn(),
  mockProcessCorrection: vi.fn(),
  mockResetPool: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    fetchCorrectionCandidates: mockFetchCandidates,
    fetchCorrectionHistory: mockFetchHistory,
    fetchCorrectionStatus: mockFetchStatus,
    processLiveCorrection: mockProcessCorrection,
    resetCorrectionPool: mockResetPool,
  };
});

describe('LiveCorrectionStudioCard (Item 128 P0)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchStatus.mockResolvedValue(FALLBACK_STATUS);
    mockFetchCandidates.mockResolvedValue(FALLBACK_CANDIDATES);
    mockFetchHistory.mockResolvedValue(FALLBACK_HISTORY);
    mockProcessCorrection.mockResolvedValue(FALLBACK_RECEIPT);
    mockResetPool.mockResolvedValue({
      service_status: 'reset_completed',
      candidates_count: 4,
      mutations_count: 0,
    });
  });

  it('renders default HUD, input form, and candidate memory nodes', async () => {
    render(<LiveCorrectionStudioCard />);

    expect(screen.getByText('实时记忆重校引擎')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('准备就绪')).toBeInTheDocument();
    });
    expect(screen.getByText('活跃候选记忆:')).toBeInTheDocument();
    expect(screen.getByText('已生效纠错数:')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/mem_pref_beverage/)).toBeInTheDocument();
      expect(screen.getByText(/mem_fact_database/)).toBeInTheDocument();
    });
  });

  it('triggers in-conversation live correction mutation successfully and displays receipt', async () => {
    render(<LiveCorrectionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('准备就绪')).toBeInTheDocument();
    });

    const submitBtn = screen.getByRole('button', { name: /即时重校/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockProcessCorrection).toHaveBeenCalledWith({
        utterance: '我不喜欢美式咖啡，换成燕麦拿铁',
      });
    });

    await waitFor(() => {
      expect(screen.getByText('即时重校执行回执 (Live Correction Receipt)')).toBeInTheDocument();
      expect(
        screen.getByText(/已为您更正偏好：由「美式咖啡」调整为「燕麦拿铁」/)
      ).toBeInTheDocument();
      expect(screen.getByText(/版本更替 \(Supersede\)/)).toBeInTheDocument();
    });
  });

  it('switches utterance using quick preset sample chips', async () => {
    render(<LiveCorrectionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('准备就绪')).toBeInTheDocument();
    });

    const sampleChip = screen.getByText('其实主数据库并非 MySQL，而是 SQLite WAL 嵌入式存储');
    fireEvent.click(sampleChip);

    const input = screen.getByPlaceholderText<HTMLInputElement>(/例如：我不喜欢美式咖啡/i);
    expect(input.value).toBe('其实主数据库并非 MySQL，而是 SQLite WAL 嵌入式存储');
  });

  it('resets candidate pool via HUD reset button', async () => {
    render(<LiveCorrectionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('准备就绪')).toBeInTheDocument();
    });

    const resetBtn = screen.getByRole('button', { name: /重置测试候选池与纠错历史/i });
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(mockResetPool).toHaveBeenCalledTimes(1);
    });
  });

  it('handles error gracefully when unrecognized utterance is processed', async () => {
    mockProcessCorrection.mockRejectedValueOnce(
      new Error('未能在该语句中识别出记忆纠错意图')
    );

    render(<LiveCorrectionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('准备就绪')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText<HTMLInputElement>(/例如：我不喜欢美式咖啡/i);
    fireEvent.change(input, { target: { value: '今天天气非常不错' } });

    const submitBtn = screen.getByRole('button', { name: /即时重校/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(
        screen.getByText(/未能在该语句中识别出记忆纠错意图/)
      ).toBeInTheDocument();
    });
  });
});
