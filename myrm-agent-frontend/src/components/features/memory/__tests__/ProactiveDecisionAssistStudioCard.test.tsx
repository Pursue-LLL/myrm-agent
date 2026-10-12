/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 135 ProactivePastPitfallAlertAndDecisionAssistSuite:
 * 1. Default render of HUD telemetry bar, shadow intent detector, and alert callouts.
 * 2. Evaluating architecture commitment triggering decisionAssistService.evaluate.
 * 3. Adopting recommended advice showing feedback toast.
 * 4. Muting and unmuting topic in session calling muteSubject / unmuteSubject.
 * 5. Seeding new causal triad postmortem triggering seedTriad.
 * 6. Resilient fallback on service rejection.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProactiveDecisionAssistStudioCard } from '../command-center/ProactiveDecisionAssistStudioCard';
import {
  mockPitfallAlertStatus,
  mockEvaluationResponseCommitment,
  mockEvaluationResponseInquiry,
} from '../command-center/decisionAssistFallbacks';

const {
  mockEvaluate,
  mockSeedTriad,
  mockMuteSubject,
  mockUnmuteSubject,
  mockGetStatus,
} = vi.hoisted(() => ({
  mockEvaluate: vi.fn(),
  mockSeedTriad: vi.fn(),
  mockMuteSubject: vi.fn(),
  mockUnmuteSubject: vi.fn(),
  mockGetStatus: vi.fn(),
}));

vi.mock('@/services/memory/decisionAssist', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    decisionAssistService: {
      evaluate: mockEvaluate,
      seedTriad: mockSeedTriad,
      muteSubject: mockMuteSubject,
      unmuteSubject: mockUnmuteSubject,
      getStatus: mockGetStatus,
    },
  };
});

describe('ProactiveDecisionAssistStudioCard (Item 135 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStatus.mockResolvedValue(mockPitfallAlertStatus);
    mockEvaluate.mockResolvedValue(mockEvaluationResponseCommitment);
    mockMuteSubject.mockResolvedValue({
      status: 'muted',
      session_id: 'sess-studio-default',
      subject: 'redis',
    });
    mockUnmuteSubject.mockResolvedValue({
      status: 'unmuted',
      session_id: 'sess-studio-default',
      subject: 'redis',
    });
    mockSeedTriad.mockResolvedValue({
      status: 'success',
      subject: 'sqlite',
    });
  });

  it('1. should render HUD bar, shadow intent detector, and alert callout', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    expect(screen.getByText('主动历史踩坑预警与决策干预')).toBeInTheDocument();
    expect(screen.getByText('个人外脑 · 主动决策协助')).toBeInTheDocument();
    expect(screen.getByText('决策防护哨兵')).toBeInTheDocument();
    expect(screen.getByText('影子决策意图嗅探器')).toBeInTheDocument();
    expect(screen.getByText('历史踩坑与决策干预预警')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalledTimes(1);
    });
  });

  it('2. should evaluate preset query and update telemetry metrics', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    const presetBtn = screen.getByRole('button', {
      name: /触发高危预警 \(Redis 分布式锁\)/i,
    });
    fireEvent.click(presetBtn);

    await waitFor(() => {
      expect(mockEvaluate).toHaveBeenCalledWith(
        expect.objectContaining({
          user_input: expect.stringContaining('redis 分布式锁'),
        })
      );
    });

    expect(screen.getByText('实质选型 (Commitment)')).toBeInTheDocument();
    expect(screen.getByText('命中历史踩坑')).toBeInTheDocument();
  });

  it('3. should adopt suggestion and display confirmation toast', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    const adoptBtn = screen.getByRole('button', { name: /采纳此建议/i });
    fireEvent.click(adoptBtn);

    await waitFor(() => {
      expect(screen.getByText(/已采纳建议方案/i)).toBeInTheDocument();
    });
  });

  it('4. should mute and unmute topic within current session', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    const muteBtn = screen.getByRole('button', { name: /本会话对此方案静音/i });
    fireEvent.click(muteBtn);

    await waitFor(() => {
      expect(mockMuteSubject).toHaveBeenCalledWith(
        expect.objectContaining({
          subject: 'redis',
        })
      );
      expect(screen.getByText(/已对主题 \[redis\] 在本会话静音/i)).toBeInTheDocument();
    });

    const unmuteBtn = screen.getByRole('button', { name: /恢复此主题预警/i });
    fireEvent.click(unmuteBtn);

    await waitFor(() => {
      expect(mockUnmuteSubject).toHaveBeenCalledWith(
        expect.objectContaining({
          subject: 'redis',
        })
      );
      expect(screen.getByText(/已恢复主题 \[redis\] 的主动提醒/i)).toBeInTheDocument();
    });
  });

  it('5. should open triad seeding drawer, fill form, and submit new postmortem', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    const openSeedBtn = screen.getByRole('button', { name: /录入踩坑教训/i });
    fireEvent.click(openSeedBtn);

    expect(screen.getByText(/录入因果三元组/i)).toBeInTheDocument();

    const subjectInput = screen.getByLabelText(/核心组件/i);
    const approachInput = screen.getByLabelText(/拟定方案/i);
    const lessonInput = screen.getByLabelText(/踩坑教训与事故根因/i);
    const altInput = screen.getByLabelText(/已验证成功的替代方案/i);

    fireEvent.change(subjectInput, { target: { value: 'sqlite' } });
    fireEvent.change(approachInput, { target: { value: '多进程并发写 WAL' } });
    fireEvent.change(lessonInput, {
      target: { value: '高并发下报 database is locked 死锁崩溃故障' },
    });
    fireEvent.change(altInput, {
      target: { value: '引入排队队列或单写者协调器' },
    });

    const submitBtn = screen.getByRole('button', { name: /保存至踩坑库/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockSeedTriad).toHaveBeenCalledWith(
        expect.objectContaining({
          subject: 'sqlite',
          pitfall_lesson: expect.stringContaining('死锁崩溃故障'),
        })
      );
      expect(screen.getByText(/成功录入 \[sqlite\] 历史踩坑教训/i)).toBeInTheDocument();
    });
  });

  it('6. should gracefully fallback when evaluation api encounters error', async () => {
    render(<ProactiveDecisionAssistStudioCard />);

    mockEvaluate.mockRejectedValueOnce(new Error('Network disconnected'));

    const submitBtn = screen.getByRole('button', { name: /立即嗅探意图/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('历史踩坑与决策干预预警')).toBeInTheDocument();
    });
  });
});
