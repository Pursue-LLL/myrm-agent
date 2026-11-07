import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentSecurityTab } from '../AgentSecurityTab';
import type { AuditResult } from '../HealthScoreCard';

const apiRequestMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({ apiRequest: apiRequestMock }));

const AUDIT: AuditResult = {
  score: 60,
  risk_level: 'medium',
  total_findings: 4,
  finding_counts: { medium: 3, info: 1 },
  findings: [
    ['Domain HITL approval not enabled', 'info'],
    ['Filesystem tools enabled without path policy', 'medium'],
    ['Network tools enabled without network policy', 'medium'],
    ['No capability restrictions configured', 'medium'],
  ].map(([title, severity]) => ({
    checker: 'policy_gap',
    severity,
    title,
    description: 'd',
    recommendation: 'r',
    source_location: '',
  })),
};

interface HostProps {
  agentId?: string | null;
  saveVersion?: number;
  onChange: (value: Record<string, unknown> | null) => void;
}

function Host({ agentId = null, saveVersion = 0, onChange }: HostProps) {
  const [value, setValue] = useState<Record<string, unknown> | null>(null);
  return (
    <AgentSecurityTab
      value={value}
      onChange={(next) => {
        onChange(next);
        setValue(next);
      }}
      defaultSecurityPreset={null}
      onDefaultSecurityPresetChange={vi.fn()}
      agentId={agentId}
      saveVersion={saveVersion}
    />
  );
}

function renderTab(props: Omit<HostProps, 'onChange'> = {}) {
  const onChange = vi.fn();
  const view = render(<Host {...props} onChange={onChange} />);
  const last = () => onChange.mock.calls[onChange.mock.calls.length - 1]?.[0];
  return { ...view, onChange, last };
}

const type = (placeholder: string, value: string) =>
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value } });
const click = (name: string) => fireEvent.click(screen.getByRole('button', { name }));
const chipOf = (text: string) => screen.getByText(text).closest('div') as HTMLElement;

beforeEach(() => {
  apiRequestMock.mockReset();
  apiRequestMock.mockResolvedValue(AUDIT);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('AgentSecurityTab list editors', () => {
  it('adds trimmed path roots, ignores blanks and duplicates, and serializes removals', () => {
    const { onChange, last } = renderTab();
    expect(screen.getByText('noAllowedRoots')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'addPath' })).toBeDisabled();

    type('pathPlaceholder', '  /data/a  ');
    click('addPath');
    expect(last()).toEqual({ pathPolicy: { allowedRoots: ['/data/a'] } });
    expect(screen.getByPlaceholderText('pathPlaceholder')).toHaveValue('');

    type('pathPlaceholder', '/data/a');
    click('addPath');
    expect(onChange).toHaveBeenCalledTimes(1);

    type('pathPlaceholder', '/data/b');
    fireEvent.keyDown(screen.getByPlaceholderText('pathPlaceholder'), { key: 'Enter' });
    expect(last()).toEqual({ pathPolicy: { allowedRoots: ['/data/a', '/data/b'] } });

    fireEvent.click(chipOf('/data/a').querySelector('button') as HTMLElement);
    expect(last()).toEqual({ pathPolicy: { allowedRoots: ['/data/b'] } });
    fireEvent.click(chipOf('/data/b').querySelector('button') as HTMLElement);
    expect(last()).toBeNull();
    expect(screen.getByText('noAllowedRoots')).toBeInTheDocument();
  });

  it('lowercases allowlist domains and toggles domain approval inside the allowlist card', () => {
    const { last } = renderTab();
    type('domainPlaceholder', ' Example.COM ');
    click('addDomain');
    expect(last()).toEqual({ networkAllowlist: ['example.com'] });

    type('domainPlaceholder', 'example.com');
    click('addDomain');
    expect(last()).toEqual({ networkAllowlist: ['example.com'] });

    const hitlSwitch = screen.getByRole('switch', { name: 'domainHitlTitle' });
    expect(document.getElementById('network-allowlist-section')).toContainElement(hitlSwitch);
    fireEvent.click(hitlSwitch);
    expect(last()).toEqual({ networkAllowlist: ['example.com'], domainHitlEnabled: true });
  });

  it('normalizes blocklist domains and reports invalid or duplicate input until the next edit', () => {
    const { last } = renderTab();
    expect(screen.getByText('noNetworkBlocklist')).toBeInTheDocument();

    type('blockedDomainPlaceholder', 'bad domain!');
    click('addBlockedDomain');
    const invalid = screen.getByText('invalidBlockedDomain');
    expect(invalid).toHaveClass('text-destructive-text');
    expect(screen.queryByText('noNetworkBlocklist')).toBeNull();
    expect(last()).toBeUndefined();

    type('blockedDomainPlaceholder', 'https://Evil.COM/path');
    expect(screen.queryByText('invalidBlockedDomain')).toBeNull();
    click('addBlockedDomain');
    expect(last()).toEqual({ networkBlocklist: ['evil.com'] });

    type('blockedDomainPlaceholder', 'evil.com');
    click('addBlockedDomain');
    expect(screen.getByText('duplicateBlockedDomain')).toBeInTheDocument();

    fireEvent.click(chipOf('evil.com').querySelector('button') as HTMLElement);
    expect(screen.queryByText('duplicateBlockedDomain')).toBeNull();
    expect(last()).toBeNull();
  });

  it('ignores a blocklist entry that normalizes to nothing', () => {
    const { onChange } = renderTab();
    type('blockedDomainPlaceholder', 'https:///only-a-path');
    click('addBlockedDomain');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.queryByText('invalidBlockedDomain')).toBeNull();
  });

  it('adds command patterns, rejects duplicates and clears the error on edit or removal', () => {
    const { last } = renderTab();
    type('commandPatternPlaceholder', '  git push --force*  ');
    click('addCommandPattern');
    expect(last()).toEqual({ commandDenylist: ['git push --force*'] });

    type('commandPatternPlaceholder', 'git push --force*');
    fireEvent.keyDown(screen.getByPlaceholderText('commandPatternPlaceholder'), { key: 'Enter' });
    expect(screen.getByText('duplicateCommandPattern')).toHaveClass('text-destructive-text');

    type('commandPatternPlaceholder', 'x');
    expect(screen.queryByText('duplicateCommandPattern')).toBeNull();

    type('commandPatternPlaceholder', 'git push --force*');
    click('addCommandPattern');
    expect(screen.getByText('duplicateCommandPattern')).toBeInTheDocument();
    fireEvent.click(chipOf('git push --force*').querySelector('button') as HTMLElement);
    expect(screen.queryByText('duplicateCommandPattern')).toBeNull();
    expect(last()).toBeNull();
  });

  it('renders danger lists with the readable destructive text token only', () => {
    renderTab();
    type('blockedDomainPlaceholder', 'evil.com');
    click('addBlockedDomain');
    type('commandPatternPlaceholder', 'rm -rf*');
    click('addCommandPattern');

    expect(screen.getByText('evil.com')).toHaveClass('text-destructive-text');
    expect(screen.getByText('rm -rf*')).toHaveClass('text-destructive-text');
    expect(screen.getByPlaceholderText('commandPatternPlaceholder')).toHaveClass('font-mono');
    expect(document.querySelector('.text-destructive')).toBeNull();
  });
});

describe('AgentSecurityTab policy controls', () => {
  it('toggles capabilities', () => {
    const { last } = renderTab();
    expect(screen.getByText('noCapabilities')).toBeInTheDocument();
    click('shell_exec');
    click('net_fetch');
    expect(last()).toEqual({ capabilities: ['shell_exec', 'net_fetch'] });
    expect(screen.queryByText('noCapabilities')).toBeNull();
    click('shell_exec');
    expect(last()).toEqual({ capabilities: ['net_fetch'] });
  });

  it('switches the injection policy between fail_closed and log_only', () => {
    const { last } = renderTab();
    const injectionSwitch = screen.getAllByRole('switch')[1];
    fireEvent.click(injectionSwitch);
    expect(last()).toEqual({ injectionPolicy: 'fail_closed' });
    fireEvent.click(injectionSwitch);
    expect(last()).toEqual({ injectionPolicy: 'log_only' });
  });

  it('clamps the approval timeout and clears it when emptied', () => {
    const { last } = renderTab();
    type('timeoutPlaceholder', '5');
    expect(last()).toEqual({ approvalTimeoutSeconds: 10 });
    type('timeoutPlaceholder', '700');
    expect(last()).toEqual({ approvalTimeoutSeconds: 600 });
    expect(screen.getByPlaceholderText('timeoutPlaceholder')).toHaveValue(600);
    type('timeoutPlaceholder', '');
    expect(last()).toBeNull();
  });
});

describe('AgentSecurityTab audit', () => {
  it('does not audit or render the score card without an agent id', async () => {
    renderTab();
    await act(async () => {});
    expect(apiRequestMock).not.toHaveBeenCalled();
    expect(screen.queryByText('healthScoreTitle')).toBeNull();
  });

  it('audits a saved agent and re-audits when the save version changes', async () => {
    const onChange = vi.fn();
    const { rerender } = render(<Host agentId="agent-1" saveVersion={0} onChange={onChange} />);
    expect(await screen.findByText('healthScoreTitle')).toBeInTheDocument();
    expect(apiRequestMock).toHaveBeenCalledWith('/user-agents/agent-1/audit', { method: 'POST', silent: true });

    rerender(<Host agentId="agent-1" saveVersion={1} onChange={onChange} />);
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('healthScoreTitle')).toBeInTheDocument();
  });

  it('drops the score card when the audit fails', async () => {
    apiRequestMock.mockRejectedValue(new Error('boom'));
    renderTab({ agentId: 'agent-1' });
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByText('healthScoreTitle')).toBeNull();
  });

  it('wires the fix actions to the domain switch and the highlighted editor cards', async () => {
    const scrollIntoView = vi.mocked(Element.prototype.scrollIntoView);
    scrollIntoView.mockClear();
    const { last } = renderTab({ agentId: 'agent-1' });
    fireEvent.click(await screen.findByText('checkers.policy_gap'));

    fireEvent.click(screen.getByRole('button', { name: 'fixAction' }));
    expect(last()).toEqual({ domainHitlEnabled: true });

    vi.useFakeTimers();
    for (const button of screen.getAllByRole('button', { name: 'configureAction' })) {
      fireEvent.click(button);
    }
    const scrolled = scrollIntoView.mock.contexts.map((el) => (el as Element).id);
    expect(scrolled).toEqual(['allowed-roots-section', 'network-allowlist-section', 'capabilities-section']);
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' });
    for (const id of scrolled) {
      expect(document.getElementById(id)).toHaveClass('ring-2', 'ring-primary/50');
    }
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    for (const id of scrolled) {
      expect(document.getElementById(id)).not.toHaveClass('ring-2');
    }
  });
});
