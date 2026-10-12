/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AutoRecallGovernanceCard } from '../command-center/AutoRecallGovernanceCard';

const {
  mockEvaluateAutoRecall,
  mockGetSlidingWindowStats,
  mockClearSessionAutoRecall,
} = vi.hoisted(() => ({
  mockEvaluateAutoRecall: vi.fn(),
  mockGetSlidingWindowStats: vi.fn(),
  mockClearSessionAutoRecall: vi.fn(),
}));

vi.mock('@/services/memory/autoRecall', () => ({
  evaluateAutoRecall: mockEvaluateAutoRecall,
  getSlidingWindowStats: mockGetSlidingWindowStats,
  clearSessionAutoRecall: mockClearSessionAutoRecall,
}));

describe('AutoRecallGovernanceCard', () => {
  const mockStats = {
    session_id: 'session_main_active',
    active_window_turns: 3,
    total_suppressed_id_count: 5,
  };

  const mockDecisionTriggered = {
    triggered: true,
    trigger_type: 'task_start',
    candidates_pre_dedup: 3,
    candidates_post_dedup: 2,
    injected_candidates: [
      {
        memory_id: 'rec-01',
        content: '在执行递归清理时，始终预检路径是否存在于沙箱工作区之内。',
        initial_score: 0.9,
      },
    ],
    reranker_status: 'reranker_skipped',
    audit_reason: 'Matched task_start scenario; 1 item suppressed by 5-turn sliding window',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSlidingWindowStats.mockResolvedValue(mockStats);
  });

  it('renders initial form inputs and sliding window HUD', async () => {
    render(<AutoRecallGovernanceCard />);

    expect(screen.getByText('高敏感场景经验自动召回与 5 轮滑窗去重门禁')).toBeInTheDocument();
    expect(screen.getByText('Fail-Open 重排降级')).toBeInTheDocument();

    expect(await screen.findByText('3 / 5 轮')).toBeInTheDocument();
    expect(screen.getByText('5 条')).toBeInTheDocument();

    expect(screen.getByLabelText(/会话标识 Session ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/当前会话轮次 Turn/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /执行门禁评估/ })).toBeInTheDocument();
  });

  it('evaluates sensitive trigger and renders audit decision funnel', async () => {
    mockEvaluateAutoRecall.mockResolvedValueOnce(mockDecisionTriggered);

    render(<AutoRecallGovernanceCard />);

    const evalBtn = screen.getByRole('button', { name: /执行门禁评估/ });
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluateAutoRecall).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('门禁审计裁决')).toBeInTheDocument();
    expect(screen.getByText('任务启动 (task_start)')).toBeInTheDocument();
    expect(screen.getByText('无 Key 静默跳过 (Fail-Open)')).toBeInTheDocument();
    expect(screen.getByText(/已通过门禁并注入 Context 的经验记忆/)).toBeInTheDocument();
    expect(screen.getByText('rec-01')).toBeInTheDocument();
  });

  it('evaluates casual chat and displays complete suppression', async () => {
    mockEvaluateAutoRecall.mockResolvedValueOnce({
      triggered: false,
      trigger_type: 'none',
      candidates_pre_dedup: 3,
      candidates_post_dedup: 0,
      injected_candidates: [],
      reranker_status: 'reranker_skipped',
      audit_reason: 'Classified as casual chat; recall completely suppressed',
    });

    render(<AutoRecallGovernanceCard />);

    const casualBtn = screen.getByRole('button', { name: /none \(闲聊日常\/完全抑制\)/ });
    fireEvent.click(casualBtn);

    const evalBtn = screen.getByRole('button', { name: /执行门禁评估/ });
    fireEvent.click(evalBtn);

    await waitFor(() => {
      expect(mockEvaluateAutoRecall).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('完全抑制 (0 召回)')).toBeInTheDocument();
  });

  it('clears session sliding window cache and resets turn', async () => {
    mockClearSessionAutoRecall.mockResolvedValueOnce({
      session_id: 'session_main_active',
      cleared: true,
    });

    render(<AutoRecallGovernanceCard />);

    const clearBtn = screen.getByRole('button', { name: /清空滑窗记录/ });
    fireEvent.click(clearBtn);

    await waitFor(() => {
      expect(mockClearSessionAutoRecall).toHaveBeenCalledWith('session_main_active');
    });

    expect(await screen.findByText(/已清空会话 session_main_active 的 5 轮滑窗记忆缓存/)).toBeInTheDocument();
  });

  it('displays error message when evaluate API fails', async () => {
    mockEvaluateAutoRecall.mockRejectedValueOnce(new Error('Network gateway timeout'));

    render(<AutoRecallGovernanceCard />);

    const evalBtn = screen.getByRole('button', { name: /执行门禁评估/ });
    fireEvent.click(evalBtn);

    expect(await screen.findByText(/错误: Network gateway timeout/)).toBeInTheDocument();
  });
});
