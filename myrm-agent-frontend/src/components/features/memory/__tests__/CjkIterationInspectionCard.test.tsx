/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 146 MnemosyneIterationMarkRecall:
 * 1. Default render of CJK iteration inspection card with header and scenario tabs.
 * 2. Displays normalized text, expansion count, and 3D token matrix for standard expansion.
 * 3. Switches to chained expansion tab and displays multi-token resolution.
 * 4. Switches to bidirectional recall tab and displays recall verdict with composite score.
 * 5. Switches to blocked antecedent tab and verifies anti-penetration security banner.
 * 6. Handles API failure gracefully via offline simulation fallback.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CjkIterationInspectionCard } from '../command-center/CjkIterationInspectionCard';
import type {
  DisambiguateCjkRequest,
  DisambiguateCjkResponse,
  MatchCjkRecallRequest,
  MatchCjkRecallResponse,
} from '@/services/memory/cjkIteration';

const { mockDisambiguate, mockMatch, mockGetHealth } = vi.hoisted(() => ({
  mockDisambiguate: vi.fn(),
  mockMatch: vi.fn(),
  mockGetHealth: vi.fn(),
}));

vi.mock('@/services/memory/cjkIteration', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    cjkIterationApi: {
      disambiguate: mockDisambiguate,
      match: mockMatch,
      getHealth: mockGetHealth.mockResolvedValue({ status: 'ok', module: 'cjk_iteration_mark', version: '1.0.0' }),
    },
  };
});

describe('CjkIterationInspectionCard (Item 146 P1)', () => {
  const sampleSingleRes: DisambiguateCjkResponse = {
    original_text: '日々の業務改善',
    normalized_text: '日日の業務改善',
    has_iteration_mark: true,
    marks_expanded_count: 1,
    runs: [
      {
        raw_run: '日々',
        expanded_run: '日日',
        expanded_indices: [1],
        raw_bigrams: ['日々'],
        normalized_bigrams: ['日日'],
        anchor_bigrams: ['日々', '日日'],
      },
    ],
    tokens: {
      raw_tokens: ['日々', '業務', '務改', '改善'],
      normalized_tokens: ['日日', '業務', '務改', '改善'],
      anchor_tokens: ['日々', '日日'],
      all_tokens: ['日々', '日日', '業務', '務改', '改善'],
    },
  };

  const sampleChainedRes: DisambiguateCjkResponse = {
    original_text: '代々々々伝承',
    normalized_text: '代代代代伝承',
    has_iteration_mark: true,
    marks_expanded_count: 3,
    runs: [],
    tokens: {
      raw_tokens: ['代々', '々々', '伝承'],
      normalized_tokens: ['代代', '代代', '伝承'],
      anchor_tokens: ['代々', '代代'],
      all_tokens: ['代々', '代代', '伝承'],
    },
  };

  const sampleBlockedRes: DisambiguateCjkResponse = {
    original_text: 'あ々 不正々',
    normalized_text: 'あ々 不正々',
    has_iteration_mark: true,
    marks_expanded_count: 0,
    runs: [],
    tokens: {
      raw_tokens: [],
      normalized_tokens: [],
      anchor_tokens: [],
      all_tokens: [],
    },
  };

  const sampleRecallMatchRes: MatchCjkRecallResponse = {
    query: '日々の反省',
    target: '日日の反省と計画策定',
    is_matched: true,
    raw_overlap_count: 1,
    normalized_overlap_count: 2,
    anchor_overlap_count: 1,
    composite_score: 0.88,
    matched_tokens: ['日日', '反省'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockDisambiguate.mockImplementation(async (req: DisambiguateCjkRequest) => {
      if (req.text.includes('代々')) {
        return sampleChainedRes;
      }
      if (req.text.includes('あ々')) {
        return sampleBlockedRes;
      }
      return sampleSingleRes;
    });
    mockMatch.mockResolvedValue(sampleRecallMatchRes);
  });

  it('renders card title, subtitle, and scenario switch buttons', async () => {
    render(<CjkIterationInspectionCard />);

    expect(screen.getByText(/CJK 叠字消歧与双向召回引擎/i)).toBeInTheDocument();
    expect(screen.getByText(/Item 146/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /标准叠字/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /多重叠字链/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /双向召回对齐/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /前驱防穿透/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(mockDisambiguate).toHaveBeenCalledWith({ text: '日々の業務改善' });
    });
  });

  it('displays resolved normalized text and 3D token matrix on default scenario', async () => {
    render(<CjkIterationInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText('日日の業務改善')).toBeInTheDocument();
      expect(screen.getByText(/展开叠字数: 1/i)).toBeInTheDocument();
      expect(screen.getByText(/三维 Token 矩阵/i)).toBeInTheDocument();
    });
  });

  it('switches to chained expansion and displays multi-token resolution', async () => {
    render(<CjkIterationInspectionCard />);

    const chainedBtn = screen.getByRole('button', { name: /多重叠字链/i });
    fireEvent.click(chainedBtn);

    await waitFor(() => {
      expect(mockDisambiguate).toHaveBeenCalledWith({ text: '代々々々伝承' });
      expect(screen.getByText('代代代代伝承')).toBeInTheDocument();
      expect(screen.getByText(/展开叠字数: 3/i)).toBeInTheDocument();
    });
  });

  it('switches to bidirectional recall and displays recall match breakdown', async () => {
    render(<CjkIterationInspectionCard />);

    const recallBtn = screen.getByRole('button', { name: /双向召回对齐/i });
    fireEvent.click(recallBtn);

    await waitFor(() => {
      expect(mockMatch).toHaveBeenCalledWith({
        query: '日々の反省',
        target_text: '日日の反省と計画策定',
        threshold: 0.1,
      });
      expect(screen.getByText(/双向召回判定结果/i)).toBeInTheDocument();
      expect(screen.getByText(/88.0%/i)).toBeInTheDocument();
      expect(screen.getByText('日日の反省と計画策定')).toBeInTheDocument();
    });
  });

  it('switches to blocked antecedent scenario and presents security notice', async () => {
    render(<CjkIterationInspectionCard />);

    const blockedBtn = screen.getByRole('button', { name: /前驱防穿透/i });
    fireEvent.click(blockedBtn);

    await waitFor(() => {
      expect(screen.getByText(/前驱安全防穿透生效/i)).toBeInTheDocument();
      expect(screen.getByText(/展开叠字数: 0/i)).toBeInTheDocument();
    });
  });

  it('falls back gracefully to offline simulation on network error', async () => {
    mockDisambiguate.mockRejectedValue(new Error('Network error'));

    render(<CjkIterationInspectionCard />);

    await waitFor(() => {
      expect(screen.getByText('日日の業務改善')).toBeInTheDocument();
      expect(screen.getByText(/展开叠字数: 1/i)).toBeInTheDocument();
    });
  });
});
