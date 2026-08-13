/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...classes: (string | boolean | undefined)[]) => classes.filter(Boolean).join(' '),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ComponentPropsWithoutRef<'button'> & { variant?: string; size?: string }) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
}));

import { HealthScoreCard, type AuditResult } from '../HealthScoreCard';

const mockT = (key: string, values?: Record<string, string | number>) => {
  if (key === 'checkerIssues' && values?.count !== undefined) {return `${values.count} issues`;}
  const translations: Record<string, string> = {
    healthScoreTitle: 'Security Health Score',
    checkerPass: 'Pass',
    fixAction: 'Fix',
    configureAction: 'Configure',
    'checkers.tool_exposure': 'Tool Exposure',
    'checkers.mcp_auth': 'MCP Security',
    'checkers.skill_aggregate': 'Skill Trust',
    'checkers.subagent_risk': 'Subagent Risk',
    'checkers.cron_risk': 'Scheduled Task Risk',
    'checkers.policy_gap': 'Policy Coverage',
  };
  return translations[key] || key;
};

const SAFE_RESULT: AuditResult = {
  score: 100,
  risk_level: 'safe',
  findings: [],
  total_findings: 0,
  finding_counts: {},
};

const RISKY_RESULT: AuditResult = {
  score: 52,
  risk_level: 'medium',
  findings: [
    { checker: 'tool_exposure', severity: 'high', title: 'Dangerous tool combination', description: 'desc', recommendation: 'rec', source_location: '' },
    { checker: 'mcp_auth', severity: 'medium', title: 'MCP no auth', description: 'desc', recommendation: 'rec', source_location: '' },
    { checker: 'policy_gap', severity: 'medium', title: 'Network tools enabled without network policy', description: 'desc', recommendation: 'Add allowlist', source_location: '' },
    { checker: 'policy_gap', severity: 'info', title: 'Domain HITL approval not enabled', description: 'desc', recommendation: 'Enable HITL', source_location: '' },
  ],
  total_findings: 4,
  finding_counts: { high: 1, medium: 2, info: 1 },
};

describe('HealthScoreCard', () => {
  it('returns null when result is null', () => {
    const { container } = render(
      <HealthScoreCard result={null} loading={false} t={mockT} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('shows loading skeleton when loading=true', () => {
    const { container } = render(
      <HealthScoreCard result={null} loading={true} t={mockT} />,
    );
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
  });

  it('renders score and risk level for safe result', () => {
    render(<HealthScoreCard result={SAFE_RESULT} loading={false} t={mockT} />);
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('safe')).toBeInTheDocument();
    expect(screen.getByText('Security Health Score')).toBeInTheDocument();
  });

  it('shows all 6 checker dimensions', () => {
    render(<HealthScoreCard result={SAFE_RESULT} loading={false} t={mockT} />);
    expect(screen.getByText('Tool Exposure')).toBeInTheDocument();
    expect(screen.getByText('MCP Security')).toBeInTheDocument();
    expect(screen.getByText('Skill Trust')).toBeInTheDocument();
    expect(screen.getByText('Subagent Risk')).toBeInTheDocument();
    expect(screen.getByText('Scheduled Task Risk')).toBeInTheDocument();
    expect(screen.getByText('Policy Coverage')).toBeInTheDocument();
  });

  it('shows Pass for dimensions without issues', () => {
    render(<HealthScoreCard result={SAFE_RESULT} loading={false} t={mockT} />);
    const passElements = screen.getAllByText('Pass');
    expect(passElements.length).toBe(6);
  });

  it('shows issue count for dimensions with findings', () => {
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />);
    const issueElements = screen.getAllByText('1 issues');
    expect(issueElements.length).toBe(2);
    expect(screen.getByText('2 issues')).toBeInTheDocument();
  });

  it('expands checker details on click', () => {
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />);
    fireEvent.click(screen.getByText('Tool Exposure'));
    expect(screen.getByText('Dangerous tool combination')).toBeInTheDocument();
    expect(screen.getByText('rec')).toBeInTheDocument();
  });

  it('collapses expanded checker on second click', () => {
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />);
    fireEvent.click(screen.getByText('Tool Exposure'));
    expect(screen.getByText('Dangerous tool combination')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Tool Exposure'));
    expect(screen.queryByText('Dangerous tool combination')).not.toBeInTheDocument();
  });

  it('does not expand pass dimensions (disabled button)', () => {
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />);
    const skillTrustBtn = screen.getByText('Skill Trust').closest('button');
    expect(skillTrustBtn).toHaveAttribute('disabled');
  });

  it('renders Fix button for policy_gap toggle findings', () => {
    const onFix = vi.fn();
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} onFixToggle={onFix} />);
    fireEvent.click(screen.getByText('Policy Coverage'));
    expect(screen.getByText('Fix')).toBeInTheDocument();
  });

  it('renders Configure button for policy_gap navigate findings', () => {
    const onFix = vi.fn();
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} onFixToggle={onFix} />);
    fireEvent.click(screen.getByText('Policy Coverage'));
    expect(screen.getByText('Configure')).toBeInTheDocument();
  });

  it('calls onFixToggle with correct targetId on Fix click', () => {
    const onFix = vi.fn();
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} onFixToggle={onFix} />);
    fireEvent.click(screen.getByText('Policy Coverage'));
    fireEvent.click(screen.getByText('Fix'));
    expect(onFix).toHaveBeenCalledWith('domain-hitl-switch');
  });

  it('calls onFixToggle with correct targetId on Configure click', () => {
    const onFix = vi.fn();
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} onFixToggle={onFix} />);
    fireEvent.click(screen.getByText('Policy Coverage'));
    fireEvent.click(screen.getByText('Configure'));
    expect(onFix).toHaveBeenCalledWith('network-allowlist-section');
  });

  it('does not render fix buttons when onFixToggle is undefined', () => {
    render(<HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />);
    fireEvent.click(screen.getByText('Policy Coverage'));
    expect(screen.queryByText('Fix')).not.toBeInTheDocument();
    expect(screen.queryByText('Configure')).not.toBeInTheDocument();
  });

  it('applies correct risk level border style', () => {
    const { container } = render(
      <HealthScoreCard result={RISKY_RESULT} loading={false} t={mockT} />,
    );
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('border-amber-500/30');
  });
});
