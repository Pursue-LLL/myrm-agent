/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NoiseFreeMemoryCard } from '../command-center/NoiseFreeMemoryCard';
import type {
  CleanDialogueResponseDTO,
  CommitFactResponseDTO,
  EpochStatusResponseDTO,
  ExtractedFactCandidateDTO,
  InspectPIIResponseDTO,
  PurgeMemoryResponseDTO,
} from '@/services/memory/noiseFreeMemory';

const {
  mockCleanDialogue,
  mockInspectPII,
  mockCommitFact,
  mockPurgeMemory,
  mockGetEpochStatus,
  mockGetUserFacts,
} = vi.hoisted(() => ({
  mockCleanDialogue: vi.fn(),
  mockInspectPII: vi.fn(),
  mockCommitFact: vi.fn(),
  mockPurgeMemory: vi.fn(),
  mockGetEpochStatus: vi.fn(),
  mockGetUserFacts: vi.fn(),
}));

vi.mock('@/services/memory/noiseFreeMemory', () => ({
  cleanDialogue: mockCleanDialogue,
  inspectPII: mockInspectPII,
  commitFact: mockCommitFact,
  purgeNoiseFreeMemory: mockPurgeMemory,
  getEpochStatus: mockGetEpochStatus,
  getUserFacts: mockGetUserFacts,
}));

describe('NoiseFreeMemoryCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockStatus: EpochStatusResponseDTO = {
    user_id: 'default_user',
    current_generation: 1,
    active_extractions: 0,
    stale_writes_dropped: 0,
    last_purged_at: null,
    stored_facts_count: 1,
    pii_violations_blocked: 0,
  };

  const mockFacts: ExtractedFactCandidateDTO[] = [
    {
      fact_id: 'fact_mock_01',
      fact_text: '用户偏好使用 TypeScript 强类型与严格单元测试',
      category: 'developer_preference',
      confidence: 0.95,
      generation_observed: 1,
    },
  ];

  it('renders correctly and loads epoch status and facts', async () => {
    mockGetEpochStatus.mockResolvedValueOnce(mockStatus);
    mockGetUserFacts.mockResolvedValueOnce(mockFacts);

    render(<NoiseFreeMemoryCard />);

    expect(screen.getByTestId('noise-free-memory-card')).toBeInTheDocument();
    expect(screen.getByText('Item 88 · P0')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('current-epoch-hud')).toHaveTextContent('Gen 1');
      expect(screen.getByText('用户偏好使用 TypeScript 强类型与严格单元测试')).toBeInTheDocument();
    });
  });

  it('updates form inputs when quick presets are clicked', async () => {
    mockGetEpochStatus.mockResolvedValueOnce(mockStatus);
    mockGetUserFacts.mockResolvedValueOnce([]);

    render(<NoiseFreeMemoryCard />);

    const factInput = screen.getByLabelText(/待检验\/待持久化记忆事实/) as HTMLInputElement;

    // Click PII card preset
    fireEvent.click(screen.getByText('敏感信用卡号 (高危 PII)'));
    expect(factInput.value).toContain('4111 1111 1111 1111');

    // Click Tool noise preset
    fireEvent.click(screen.getByText('外部工具商品 JSON (噪声)'));
    expect(factInput.value).toContain('促销商品 JSON');

    // Click Clean preset
    fireEvent.click(screen.getByText('纯净用户偏好 (合规)'));
    expect(factInput.value).toContain('用户偏好深色界面主题');
  });

  it('executes tool-noise physical stripping and displays clean transcript', async () => {
    mockGetEpochStatus.mockResolvedValue(mockStatus);
    mockGetUserFacts.mockResolvedValue([]);
    const cleanResp: CleanDialogueResponseDTO = {
      user_id: 'default_user',
      clean_transcript: 'User: 我想买一双黑色跑鞋 42 码。\n\nAssistant: 已为您找到库存充足的黑色跑鞋 42 码。',
      observed_generation: 1,
      tokens_saved: 58,
      stripped_turns_count: 1,
    };
    mockCleanDialogue.mockResolvedValueOnce(cleanResp);

    render(<NoiseFreeMemoryCard />);

    const stripBtn = screen.getByText('工具噪声物理剥离演练');
    fireEvent.click(stripBtn);

    await waitFor(() => {
      expect(mockCleanDialogue).toHaveBeenCalled();
      expect(screen.getByText(/纯净自然语言上下文/)).toBeInTheDocument();
      expect(screen.getByText('节省约 58 Token')).toBeInTheDocument();
    });
  });

  it('inspects statement against PII regex gateway and catches violation', async () => {
    mockGetEpochStatus.mockResolvedValue(mockStatus);
    mockGetUserFacts.mockResolvedValue([]);
    const piiResp: InspectPIIResponseDTO = {
      is_clean: false,
      sanitized_text: '用户的卡号是 [credit_card_REDACTED]',
      violations: [
        {
          rule_name: 'credit_card',
          snippet_masked: '4111********1111',
          severity: 'high',
        },
      ],
    };
    mockInspectPII.mockResolvedValueOnce(piiResp);

    render(<NoiseFreeMemoryCard />);

    const piiBtn = screen.getByText('PII 正则前置筛查');
    fireEvent.click(piiBtn);

    await waitFor(() => {
      expect(mockInspectPII).toHaveBeenCalled();
      expect(screen.getByText(/命中高危 PII 正则规则拦截/)).toBeInTheDocument();
      expect(screen.getByText('credit_card')).toBeInTheDocument();
    });
  });

  it('commits clean fact and refreshes facts list', async () => {
    mockGetEpochStatus.mockResolvedValue(mockStatus);
    mockGetUserFacts.mockResolvedValue([]);
    const commitResp: CommitFactResponseDTO = {
      success: true,
      message: '事实已通过代次核验与 PII 门禁并成功入库',
    };
    mockCommitFact.mockResolvedValueOnce(commitResp);

    render(<NoiseFreeMemoryCard />);

    const commitBtn = screen.getByText('代次核验并入库');
    fireEvent.click(commitBtn);

    await waitFor(() => {
      expect(mockCommitFact).toHaveBeenCalledWith(
        expect.objectContaining({
          candidate: expect.objectContaining({
            fact_text: '用户偏好深色模式，常用 Python 编写测试',
            generation_observed: 1,
          }),
        })
      );
      expect(screen.getByText('事实已通过代次核验与 PII 门禁并成功入库')).toBeInTheDocument();
    });
  });

  it('purges memory and bumps generation epoch', async () => {
    mockGetEpochStatus.mockResolvedValue(mockStatus);
    mockGetUserFacts.mockResolvedValue(mockFacts);
    const purgeResp: PurgeMemoryResponseDTO = {
      user_id: 'default_user',
      new_generation: 2,
      purged_facts_count: 1,
      timestamp: '2026-10-08T03:00:00Z',
    };
    mockPurgeMemory.mockResolvedValueOnce(purgeResp);

    render(<NoiseFreeMemoryCard />);

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('current-epoch-hud')).toHaveTextContent('Gen 1');
      expect(screen.getByText('用户偏好使用 TypeScript 强类型与严格单元测试')).toBeInTheDocument();
    });

    // Mock next fetch calls after purge
    mockGetEpochStatus.mockResolvedValue({
      ...mockStatus,
      current_generation: 2,
      stored_facts_count: 0,
      last_purged_at: '2026-10-08T03:00:00Z',
    });
    mockGetUserFacts.mockResolvedValue([]);

    const purgeBtn = screen.getByText('清空记忆并自增代次 (Epoch Bump)');
    fireEvent.click(purgeBtn);

    await waitFor(() => {
      expect(mockPurgeMemory).toHaveBeenCalled();
      expect(screen.getByText(/记忆已彻底清空，代次自增/)).toBeInTheDocument();
      expect(screen.getByTestId('current-epoch-hud')).toHaveTextContent('Gen 2');
      expect(screen.getByText('当前代次暂无存储的记忆事实（已清空或尚未抽取）')).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully with fallback state', async () => {
    mockGetEpochStatus.mockRejectedValue(new Error('Network error'));
    mockGetUserFacts.mockRejectedValue(new Error('Network error'));

    render(<NoiseFreeMemoryCard />);

    // Renders without crashing and falls back to mock status and facts
    expect(screen.getByTestId('noise-free-memory-card')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('current-epoch-hud')).toHaveTextContent('Gen 1');
      expect(screen.getByText('用户偏好使用 TypeScript 强类型与严格单元测试')).toBeInTheDocument();
    });
  });
});
