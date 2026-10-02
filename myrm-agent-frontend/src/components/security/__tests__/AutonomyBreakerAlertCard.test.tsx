import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AutonomyBreakerAlertCard } from '../AutonomyBreakerAlertCard';
import type { AutonomyBreakerIncident } from '../types';

describe('AutonomyBreakerAlertCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockIncident: AutonomyBreakerIncident = {
    incidentId: 'incident_breaker_001',
    sessionId: 'session_pytest_refactor',
    reason: '连续两次单测失败且产生重试死循环',
    errorDetails: 'AssertionError: test_query failed on line 42\nCommand failed with exit code 1',
    triggeredTool: 'bash_code_execute_tool',
    previousLevel: 4,
    degradedLevel: 2,
    breakerState: 'open',
    consecutiveFailures: 2,
    timestamp: '2026-10-01 18:20:00',
  };

  it('renders alert card correctly with zero native emoji', () => {
    render(<AutonomyBreakerAlertCard incident={mockIncident} />);

    expect(screen.getByText('自主执行断路器跳闸熔断')).toBeDefined();
    expect(screen.getByText('10ms 物理阻断')).toBeDefined();
    expect(screen.getByText('熔断原因: 连续两次单测失败且产生重试死循环')).toBeDefined();
    expect(screen.getByText('触发工具: bash_code_execute_tool')).toBeDefined();
    expect(screen.getByText('(连续失败 2 次)')).toBeDefined();

    // Verify zero native emoji
    const cardEl = screen.getByTestId('autonomy-breaker-alert-card');
    const emojiRegex = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
    expect(emojiRegex.test(cardEl.textContent || '')).toBe(false);
  });

  it('toggles diagnostic error details expansion', () => {
    render(<AutonomyBreakerAlertCard incident={mockIncident} />);

    // Initially collapsed
    expect(screen.queryByTestId('breaker-error-details')).toBeNull();

    // Click toggle button
    const toggleBtn = screen.getByTestId('toggle-details-btn');
    fireEvent.click(toggleBtn);

    // Now expanded
    expect(screen.getByTestId('breaker-error-details')).toBeDefined();
    expect(screen.getByText(/test_query failed on line 42/)).toBeDefined();

    // Click again to collapse
    fireEvent.click(toggleBtn);
    expect(screen.queryByTestId('breaker-error-details')).toBeNull();
  });

  it('handles acknowledge and recover action with debounce protection', async () => {
    let resolveRecover: () => void = () => {};
    const recoverPromise = new Promise<void>((resolve) => {
      resolveRecover = resolve;
    });
    const handleRecover = vi.fn().mockReturnValue(recoverPromise);

    render(<AutonomyBreakerAlertCard incident={mockIncident} onAcknowledgeAndRecover={handleRecover} />);

    const recoverBtn = screen.getByTestId('recover-btn');

    // Click multiple times to test debounce / in-flight protection
    fireEvent.click(recoverBtn);
    fireEvent.click(recoverBtn);
    fireEvent.click(recoverBtn);

    expect(handleRecover).toHaveBeenCalledTimes(1);
    expect(handleRecover).toHaveBeenCalledWith('incident_breaker_001');

    // Resolve the promise
    resolveRecover();

    await waitFor(() => {
      expect(screen.getByTestId('autonomy-breaker-resolved')).toBeDefined();
      expect(screen.getByText(/已确认恢复执行/)).toBeDefined();
    });
  });

  it('handles manual degrade action correctly', async () => {
    const handleDegrade = vi.fn().mockResolvedValue(undefined);

    render(<AutonomyBreakerAlertCard incident={mockIncident} onDegradeToManual={handleDegrade} />);

    const degradeBtn = screen.getByTestId('degrade-btn');
    fireEvent.click(degradeBtn);

    expect(handleDegrade).toHaveBeenCalledTimes(1);
    expect(handleDegrade).toHaveBeenCalledWith('incident_breaker_001');

    await waitFor(() => {
      expect(screen.getByTestId('autonomy-breaker-resolved')).toBeDefined();
      expect(screen.getByText(/已确认降级/)).toBeDefined();
    });
  });

  it('calls onViewAudit when audit button is clicked', () => {
    const handleViewAudit = vi.fn();
    render(<AutonomyBreakerAlertCard incident={mockIncident} onViewAudit={handleViewAudit} />);

    const auditBtn = screen.getByText('审计记录');
    fireEvent.click(auditBtn);
    expect(handleViewAudit).toHaveBeenCalledTimes(1);
  });
});
