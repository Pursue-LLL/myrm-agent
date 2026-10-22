'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  RalphRoundLoopPanel,
  RalphSessionData,
} from '../RalphRoundLoopPanel';

const mockSessionData: RalphSessionData = {
  sessionId: 'ralph-sess-9901',
  humanGoal: '重构并迁移认证层至标准 OIDC 流',
  workspaceRoot: '/sandbox/repos/auth-core',
  currentRound: 2,
  maxRounds: 5,
  minRoundsBeforeBlocked: 3,
  status: 'in_progress',
  rounds: [
    {
      roundIndex: 1,
      childSessionId: 'child-agent-01',
      handoff: {
        status: 'in_progress',
        summary: '梳理既有 OAuth 表结构并完成 OIDC 发现端点接入',
        evidence: 'src/oidc/discovery.py, tests/test_discovery.py: 4 passed',
        nextSteps: '实现 JWT Token 签名与公钥 JWKS 导出接口',
        blocker: '公钥缓存穿透问题',
      },
      durationSeconds: 14.5,
      tokensConsumed: 4120,
      wasBlockedDowngraded: true,
    },
  ],
  nextDirective: '=== RALPH FRESH AGENT ROUND DIRECTIVE ===\nRound: 2 / 5\nContext Status: FRESH',
};

describe('RalphRoundLoopPanel', () => {
  it('renders panel header, fresh context badge, and immutable human goal', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    expect(screen.getByTestId('ralph-round-loop-panel')).toBeInTheDocument();
    expect(screen.getByText('Ralph Fresh-Agent 多轮循环')).toBeInTheDocument();
    expect(screen.getByText('Fresh Context 零会话历史')).toBeInTheDocument();
    expect(screen.getByText(/ralph-sess-9901/)).toBeInTheDocument();
    expect(screen.getByText(/重构并迁移认证层至标准 OIDC 流/)).toBeInTheDocument();
  });

  it('renders round stepper and marks completed and current rounds', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    const stepper = screen.getByTestId('round-stepper');
    expect(stepper).toBeInTheDocument();
    expect(screen.getByText('Round 1')).toBeInTheDocument();
    expect(screen.getByText('Round 2')).toBeInTheDocument();
    expect(screen.getByText('Round 5')).toBeInTheDocument();
  });

  it('renders structured 5-field handoff details for completed round', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    expect(screen.getByTestId('round-detail-card')).toBeInTheDocument();
    expect(screen.getByText('1. Summary (本轮执行摘要)')).toBeInTheDocument();
    expect(screen.getByText(/梳理既有 OAuth 表结构/)).toBeInTheDocument();

    expect(screen.getByText('2. Evidence (产物与验证凭据)')).toBeInTheDocument();
    expect(screen.getByText(/src\/oidc\/discovery.py/)).toBeInTheDocument();

    expect(screen.getByText('3. Next Steps (指引下一轮全新子 Agent)')).toBeInTheDocument();
    expect(screen.getByText(/实现 JWT Token 签名/)).toBeInTheDocument();

    expect(screen.getByText('4. Blocker (阻塞原因)')).toBeInTheDocument();
    expect(screen.getByText('公钥缓存穿透问题')).toBeInTheDocument();

    expect(screen.getByText('4,120 Tokens')).toBeInTheDocument();
  });

  it('renders Min-3-Round guardrail downgrade banner when wasBlockedDowngraded is true', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    const banner = screen.getByTestId('guardrail-downgraded-banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent('[Ralph Guardrail 拦截]');
    expect(banner).toHaveTextContent('未满 3 轮门槛禁止声明 BLOCKED');
  });

  it('renders empty waiting state when selecting an unfinished round', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    const round2Button = screen.getByRole('button', { name: /Round 2/ });
    fireEvent.click(round2Button);

    expect(screen.getByTestId('round-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/第 2 轮尚未完成交接/)).toBeInTheDocument();
  });

  it('toggles next round directive preview accordion', () => {
    render(<RalphRoundLoopPanel session={mockSessionData} />);

    expect(screen.queryByTestId('next-directive-content')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('toggle-directive-button');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('next-directive-content')).toBeInTheDocument();
    expect(screen.getByText(/=== RALPH FRESH AGENT ROUND DIRECTIVE ===/)).toBeInTheDocument();
  });

  it('triggers onRefresh when clicking refresh button', () => {
    const handleRefresh = vi.fn();
    render(<RalphRoundLoopPanel session={mockSessionData} onRefresh={handleRefresh} />);

    const refreshBtn = screen.getByTestId('refresh-button');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });
});
