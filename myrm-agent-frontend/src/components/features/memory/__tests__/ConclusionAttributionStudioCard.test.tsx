/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 141 ConclusionAttributionAndChatEvidenceSuite:
 * 1. Default render of HUD telemetry bar, attribution filter buttons, and conclusions list.
 * 2. Filtering conclusions by attribution level (explicit, deductive).
 * 3. Triggering downward premise traversal (walkDownwardTree).
 * 4. Triggering upward derivation traversal (walkUpwardTree).
 * 5. Triggering ripple impact assessment (getRippleImpact).
 * 6. Deleting conclusion and updating view.
 * 7. Simulating chat with verifiable ChatEvidence package.
 * 8. Resilient fallback on service rejection.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConclusionAttributionStudioCard } from '../command-center/ConclusionAttributionStudioCard';

const {
  mockGetStats,
  mockListConclusions,
  mockWalkDownwardTree,
  mockWalkUpwardTree,
  mockGetRippleImpact,
  mockDeleteConclusion,
  mockChatWithEvidence,
} = vi.hoisted(() => ({
  mockGetStats: vi.fn(),
  mockListConclusions: vi.fn(),
  mockWalkDownwardTree: vi.fn(),
  mockWalkUpwardTree: vi.fn(),
  mockGetRippleImpact: vi.fn(),
  mockDeleteConclusion: vi.fn(),
  mockChatWithEvidence: vi.fn(),
}));

vi.mock('@/services/memory/conclusionAttribution', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    conclusionAttributionApi: {
      getStats: mockGetStats,
      listConclusions: mockListConclusions,
      walkDownwardTree: mockWalkDownwardTree,
      walkUpwardTree: mockWalkUpwardTree,
      getRippleImpact: mockGetRippleImpact,
      deleteConclusion: mockDeleteConclusion,
      chatWithEvidence: mockChatWithEvidence,
    },
  };
});

describe('ConclusionAttributionStudioCard (Item 141 P1)', () => {
  const sampleStats = {
    total_conclusions: 4,
    explicit_count: 2,
    deductive_count: 2,
    inductive_count: 0,
    contradiction_count: 0,
    max_derivation_depth: 2,
    average_times_derived: 1.5,
  };

  const sampleConclusions = [
    {
      id: 'conc_101',
      peer_id: 'alice',
      content: 'Alice 坚持使用紧凑代码格式',
      level: 'explicit',
      source_ids: [],
      times_derived: 2,
      confidence: 0.99,
      created_at: new Date().toISOString(),
    },
    {
      id: 'conc_102',
      peer_id: 'alice',
      content: '前端与后端均严格执行零 Any 类型安全规范',
      level: 'deductive',
      source_ids: ['conc_101'],
      times_derived: 1,
      confidence: 0.95,
      created_at: new Date().toISOString(),
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStats.mockResolvedValue(sampleStats);
    mockListConclusions.mockResolvedValue({
      items: sampleConclusions,
      total: 2,
      page: 1,
      size: 50,
    });
    mockWalkDownwardTree.mockResolvedValue({
      root_id: 'conc_102',
      direction: 'downward',
      nodes: [
        {
          conclusion: sampleConclusions[1],
          depth: 0,
          direct_parent_ids: [],
          direct_child_ids: ['conc_101'],
        },
        {
          conclusion: sampleConclusions[0],
          depth: 1,
          direct_parent_ids: ['conc_102'],
          direct_child_ids: [],
        },
      ],
      total_nodes: 2,
    });
    mockWalkUpwardTree.mockResolvedValue({
      root_id: 'conc_101',
      direction: 'upward',
      nodes: [
        {
          conclusion: sampleConclusions[0],
          depth: 0,
          direct_parent_ids: [],
          direct_child_ids: ['conc_102'],
        },
      ],
      total_nodes: 1,
    });
    mockGetRippleImpact.mockResolvedValue({
      target_conclusion_id: 'conc_101',
      impacted_conclusion_ids: ['conc_102'],
      depth_reached: 1,
      severity: 'medium',
      explanation: '影响 1 条派生推论',
    });
    mockDeleteConclusion.mockResolvedValue({
      deleted_ids: ['conc_101'],
      cascade: false,
      status: 'deleted',
    });
    mockChatWithEvidence.mockResolvedValue({
      reply: '根据显式记忆：Alice 坚持使用紧凑代码格式',
      evidence: {
        conclusions: [sampleConclusions[0]],
        messages: [
          {
            message_id: 'msg_99',
            session_id: 'sess_1',
            role: 'user',
            snippet: '紧凑格式',
          },
        ],
        tool_calls: [],
      },
    });
  });

  it('renders studio card header, HUD bar, and initial conclusions', async () => {
    render(<ConclusionAttributionStudioCard />);

    expect(screen.getByText('记忆结论归因与证据链可视化工作台')).toBeInTheDocument();
    expect(screen.getByText('Item 141 · P1')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    });
    expect(screen.getByText('前端与后端均严格执行零 Any 类型安全规范')).toBeInTheDocument();
  });

  it('filters conclusions by derivation level button', async () => {
    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    });

    const explicitFilterBtn = screen.getByRole('button', { name: 'EXPLICIT' });
    fireEvent.click(explicitFilterBtn);

    expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    expect(screen.queryByText('前端与后端均严格执行零 Any 类型安全规范')).not.toBeInTheDocument();
  });

  it('triggers walk downward tree and displays premise hierarchy', async () => {
    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('前端与后端均严格执行零 Any 类型安全规范')).toBeInTheDocument();
    });

    const downwardBtn = screen.getByRole('button', { name: '查看conc_102前提树' });
    fireEvent.click(downwardBtn);

    await waitFor(() => {
      expect(mockWalkDownwardTree).toHaveBeenCalledWith('conc_102');
      expect(screen.getByText(/向下前提溯源树/)).toBeInTheDocument();
    });
  });

  it('triggers walk upward tree and displays derivation hierarchy', async () => {
    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    });

    const upwardBtn = screen.getByRole('button', { name: '查看conc_101派生树' });
    fireEvent.click(upwardBtn);

    await waitFor(() => {
      expect(mockWalkUpwardTree).toHaveBeenCalledWith('conc_101');
      expect(screen.getAllByText(/向上派生推论树/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('triggers ripple impact evaluation and displays severity', async () => {
    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    });

    const rippleBtn = screen.getByRole('button', { name: '评估conc_101涟漪影响' });
    fireEvent.click(rippleBtn);

    await waitFor(() => {
      expect(mockGetRippleImpact).toHaveBeenCalledWith('conc_101');
      expect(screen.getByText(/修改\/撤回涟漪影响评估/)).toBeInTheDocument();
      expect(screen.getByText('MEDIUM')).toBeInTheDocument();
    });
  });

  it('triggers delete conclusion after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('Alice 坚持使用紧凑代码格式')).toBeInTheDocument();
    });

    const deleteBtn = screen.getByRole('button', { name: '删除conc_101' });
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(mockDeleteConclusion).toHaveBeenCalledWith('conc_101', false);
    });
  });

  it('simulates chat with transparent evidence package', async () => {
    render(<ConclusionAttributionStudioCard />);

    const input = screen.getByPlaceholderText(/输入测试提问/);
    fireEvent.change(input, { target: { value: '代码格式' } });

    const chatBtn = screen.getByRole('button', { name: /透明推理/ });
    fireEvent.click(chatBtn);

    await waitFor(() => {
      expect(mockChatWithEvidence).toHaveBeenCalledWith({
        query: '代码格式',
        peer_id: 'alice',
        include_evidence: true,
      });
      expect(screen.getByText(/根据显式记忆：Alice 坚持使用紧凑代码格式/)).toBeInTheDocument();
      expect(screen.getByText(/Verifiable Evidence Package/)).toBeInTheDocument();
    });
  });

  it('falls back safely when service errors out', async () => {
    mockGetStats.mockRejectedValue(new Error('Network error'));
    mockListConclusions.mockRejectedValue(new Error('Network error'));

    render(<ConclusionAttributionStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('记忆结论归因与证据链可视化工作台')).toBeInTheDocument();
    });
  });
});
