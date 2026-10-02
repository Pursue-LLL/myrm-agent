import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CapabilityAttenuationCapsule, type AttenuatedCapabilityInfo } from '../CapabilityAttenuationCapsule';
import { CapabilityViolationAlertCard, type CapabilityViolationIncident } from '../CapabilityViolationAlertCard';

describe('CapabilityAttenuationCapsule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockReadOnlyCap: AttenuatedCapabilityInfo = {
    handleId: 'cap_ro_998877665544',
    subjectId: 'subagent_code_reviewer',
    actions: ['read'],
    paths: ['/workspace/src/core'],
    domains: ['api.github.com'],
    remainingTtlSeconds: 120,
  };

  const mockMultiCap: AttenuatedCapabilityInfo = {
    handleId: 'cap_rw_112233445566',
    subjectId: 'subagent_builder',
    actions: ['read', 'write', 'execute'],
    paths: ['/workspace/build'],
    remainingTtlSeconds: 45,
  };

  it('renders read-only capsule correctly with zero emoji', () => {
    render(<CapabilityAttenuationCapsule capability={mockReadOnlyCap} />);

    expect(screen.getByText('只读受限沙箱')).toBeDefined();
    expect(screen.getByText('120s')).toBeDefined();

    // Verify zero emoji
    const capsuleEl = screen.getByTestId('capability-attenuation-capsule');
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(capsuleEl.textContent || '')).toBe(false);
  });

  it('renders zero-trust ocap label for multi-action capability', () => {
    render(<CapabilityAttenuationCapsule capability={mockMultiCap} />);

    expect(screen.getByText('零信任 OCap 拘禁')).toBeDefined();
    expect(screen.getByText('45s')).toBeDefined();
  });

  it('toggles expansion drawer showing details and actions', () => {
    render(<CapabilityAttenuationCapsule capability={mockReadOnlyCap} />);

    // Initially collapsed
    expect(screen.queryByText('cap_ro_998877665544')).toBeNull();

    // Expand
    const toggleButton = screen.getByRole('button', { name: /查看细粒度安全授权范围/i });
    fireEvent.click(toggleButton);

    expect(screen.getByText('cap_ro_998877665544')).toBeDefined();
    expect(screen.getByText('READ')).toBeDefined();
    expect(screen.getByText('/workspace/src/core')).toBeDefined();
    expect(screen.getByText('api.github.com')).toBeDefined();

    // Collapse
    fireEvent.click(toggleButton);
    expect(screen.queryByText('cap_ro_998877665544')).toBeNull();
  });
});

describe('CapabilityViolationAlertCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockIncident: CapabilityViolationIncident = {
    incidentId: 'inc_violation_403_8899',
    capabilityId: 'cap_subagent_worker_7766',
    subagentRole: 'UnitTestRunner',
    action: 'write',
    target: '/etc/shadow',
    violationReason: 'Path /etc/shadow is strictly outside the authorized boundary /workspace/tests',
    interceptedAt: '2026-10-01 16:30:00',
  };

  it('renders violation alert card with zero emoji and correct warning details', () => {
    render(<CapabilityViolationAlertCard incident={mockIncident} />);

    expect(screen.getByText('零信任 OCap 拘禁：越界调用已被拦截')).toBeDefined();
    expect(screen.getByText('强制阻断 (Fail-Closed)')).toBeDefined();
    expect(screen.getByText(/WRITE \(写入未授权路径\)/)).toBeDefined();
    expect(screen.getByText('UnitTestRunner')).toBeDefined();
    expect(screen.getByText('/etc/shadow')).toBeDefined();
    expect(screen.getByText(/16:30:00/)).toBeDefined();

    // Zero emoji check
    const cardEl = screen.getByTestId('capability-violation-alert-card');
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(cardEl.textContent || '')).toBe(false);
  });

  it('expands technical evidence drawer when button is clicked', () => {
    render(<CapabilityViolationAlertCard incident={mockIncident} />);

    expect(screen.queryByText(/is strictly outside the authorized boundary/)).toBeNull();

    const expandBtn = screen.getByText('展开证据链');
    fireEvent.click(expandBtn);

    expect(screen.getByText(/is strictly outside the authorized boundary/)).toBeDefined();
    expect(screen.getByText('cap_subagent_worker_7766')).toBeDefined();
    expect(screen.getByText('Object-Capability Non-Forging Token')).toBeDefined();

    const collapseBtn = screen.getByText('收起详情');
    fireEvent.click(collapseBtn);
    expect(screen.queryByText(/is strictly outside the authorized boundary/)).toBeNull();
  });

  it('handles dismiss action and updates UI', () => {
    const onDismiss = vi.fn();
    render(<CapabilityViolationAlertCard incident={mockIncident} onDismiss={onDismiss} />);

    const dismissBtn = screen.getByText('我知道了并确认安全');
    fireEvent.click(dismissBtn);

    expect(onDismiss).toHaveBeenCalledWith('inc_violation_403_8899');
    expect(screen.getByTestId('capability-violation-alert-dismissed')).toBeDefined();
    expect(screen.getByText(/该越界调用已拦截并确认为安全隔离事件/)).toBeDefined();
  });

  it('triggers onViewAudit callback when audit button clicked', () => {
    const onViewAudit = vi.fn();
    render(<CapabilityViolationAlertCard incident={mockIncident} onViewAudit={onViewAudit} />);

    const auditBtn = screen.getByText('查看安全审计详情');
    fireEvent.click(auditBtn);

    expect(onViewAudit).toHaveBeenCalledTimes(1);
  });

  it('triggers onRevoke and updates UI to revoked state', async () => {
    const onRevoke = vi.fn().mockResolvedValue(undefined);
    render(<CapabilityViolationAlertCard incident={mockIncident} onRevoke={onRevoke} />);

    const revokeBtn = screen.getByTestId('capability-revoke-button');
    expect(revokeBtn).toBeDefined();
    expect(screen.getByText('立即撤销授权并熔断')).toBeDefined();

    fireEvent.click(revokeBtn);
    expect(onRevoke).toHaveBeenCalledWith('cap_subagent_worker_7766');

    const revokedBadge = await screen.findByTestId('capability-violation-alert-revoked');
    expect(revokedBadge).toBeDefined();
    expect(screen.getByText(/该权能句柄已即时级联撤销并熔断/)).toBeDefined();
  });
});
