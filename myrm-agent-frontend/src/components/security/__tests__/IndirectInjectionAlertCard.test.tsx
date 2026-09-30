import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { IndirectInjectionAlertCard, type IndirectInjectionIncident } from '../IndirectInjectionAlertCard';

describe('IndirectInjectionAlertCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockIncident: IndirectInjectionIncident = {
    sessionId: 'sess_test_123',
    sourceDomain: 'malicious-prompt-injection.org',
    detectedAt: '2026-09-28T23:00:00Z',
  };

  it('renders initial active threat state correctly with zero emoji', () => {
    render(<IndirectInjectionAlertCard incident={mockIncident} />);

    expect(screen.getByText('安全主动防御：非受信网页威胁已阻断')).toBeDefined();
    expect(screen.getByText('主动硬拦截')).toBeDefined();
    expect(screen.getByText('malicious-prompt-injection.org')).toBeDefined();
    expect(screen.getByText('净化受污染上下文并继续')).toBeDefined();

    // Verify zero emoji in alert container
    const containerText = screen.getByRole('alert').textContent || '';
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(containerText)).toBe(false);
  });

  it('toggles technical details drawer correctly', () => {
    render(<IndirectInjectionAlertCard incident={mockIncident} />);

    expect(screen.queryByText('Loopback Egress Honeytoken Trap')).toBeNull();

    // Click to show details
    const detailsButton = screen.getByText('技术详情');
    fireEvent.click(detailsButton);

    expect(screen.getByText('Loopback Egress Honeytoken Trap')).toBeDefined();
    expect(screen.getByText('TCP Socket RST (Fail-Closed)')).toBeDefined();
    expect(screen.getByText('100% 保持命中')).toBeDefined();

    // Click to collapse
    const collapseButton = screen.getByText('收起详情');
    fireEvent.click(collapseButton);
    expect(screen.queryByText('Loopback Egress Honeytoken Trap')).toBeNull();
  });

  it('triggers onRemediate and transitions to resolved state', async () => {
    const onRemediate = vi.fn().mockResolvedValue(undefined);
    render(<IndirectInjectionAlertCard incident={mockIncident} onRemediate={onRemediate} />);

    const remediateButton = screen.getByText('净化受污染上下文并继续');
    fireEvent.click(remediateButton);

    await waitFor(() => {
      expect(onRemediate).toHaveBeenCalledWith('sess_test_123');
      expect(screen.getByText('外部威胁已隔离并恢复安全')).toBeDefined();
      expect(screen.getByText('已自愈')).toBeDefined();
      expect(screen.getByText('会话已恢复安全')).toBeDefined();
    });
  });

  it('calls onViewAudit when audit log button is clicked', () => {
    const onViewAudit = vi.fn();
    render(<IndirectInjectionAlertCard incident={mockIncident} onViewAudit={onViewAudit} />);

    const auditButton = screen.getByText('安全日志');
    fireEvent.click(auditButton);
    expect(onViewAudit).toHaveBeenCalledTimes(1);
  });
});
