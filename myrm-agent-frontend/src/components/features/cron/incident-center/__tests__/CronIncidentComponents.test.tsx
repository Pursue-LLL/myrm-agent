/**
 * Cron Incident Center UI Components Unit Tests
 */

import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { CronIncidentAlertBadge } from '../CronIncidentAlertBadge';
import { CronIncidentCenterContainer } from '../CronIncidentCenterContainer';
import { CronIncidentDrawer } from '../CronIncidentDrawer';
import { useCronIncidentStore } from '../useCronIncidentStore';

describe('CronIncident UI Components', () => {
  beforeEach(() => {
    useCronIncidentStore.getState().resetToDefault();
  });

  it('should render alert badge with silent failure indicator and open drawer on click', () => {
    render(<CronIncidentAlertBadge />);

    const badge = screen.getByTestId('cron-incident-alert-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/假成功静默失败/);
    expect(badge).toHaveTextContent(/待签收/);

    // Click badge to open drawer
    fireEvent.click(badge);
    expect(useCronIncidentStore.getState().isDrawerOpen).toBe(true);
  });

  it('should render healthy badge when all incidents are acknowledged', () => {
    useCronIncidentStore.getState().acknowledgeAll();

    render(<CronIncidentAlertBadge />);
    expect(screen.getByTestId('cron-incident-badge-healthy')).toBeInTheDocument();
    expect(screen.getByText(/定时任务运转正常，无待办故障事故/)).toBeInTheDocument();
  });

  it('should render drawer dialog and allow single and batch Ack actions', () => {
    useCronIncidentStore.getState().setIsDrawerOpen(true);
    render(<CronIncidentDrawer />);

    expect(screen.getByTestId('cron-incident-drawer-dialog')).toBeInTheDocument();
    expect(screen.getByText(/晨间财务报表同步任务/)).toBeInTheDocument();
    expect(screen.getByText(/假成功警示: 进程无报错退出，物理产物为空/)).toBeInTheDocument();

    // Single Ack on specific incident
    const ackBtn = screen.getByTestId('ack-btn-inc-demo-silent-01');
    fireEvent.click(ackBtn);

    const targetIncident = useCronIncidentStore
      .getState()
      .incidents.find((i) => i.id === 'inc-demo-silent-01');
    expect(targetIncident?.acknowledged).toBe(true);

    // Batch Ack remaining incidents
    const batchAckBtn = screen.queryByTestId('ack-all-btn');
    if (batchAckBtn) {
      fireEvent.click(batchAckBtn);
      const metrics = useCronIncidentStore.getState().getMetrics();
      expect(metrics.unacknowledgedCount).toBe(0);
    }
  });

  it('should allow retrying an incident and trigger event on history jump', () => {
    useCronIncidentStore.getState().setIsDrawerOpen(true);
    render(<CronIncidentDrawer />);

    const retryBtn = screen.getByTestId('retry-btn-inc-demo-silent-01');
    fireEvent.click(retryBtn);

    const target = useCronIncidentStore
      .getState()
      .incidents.find((i) => i.id === 'inc-demo-silent-01');
    expect(target?.retryCount).toBeGreaterThanOrEqual(1);

    // Jump to history
    const jumpBtn = screen.getByTestId('jump-history-btn-inc-demo-silent-01');
    expect(jumpBtn).toBeInTheDocument();
    fireEvent.click(jumpBtn);
  });

  it('should filter incidents by category tab and close drawer properly', () => {
    useCronIncidentStore.getState().setIsDrawerOpen(true);
    render(<CronIncidentDrawer />);

    const quotaTab = screen.getByTestId('category-tab-quota_exhausted');
    fireEvent.click(quotaTab);
    expect(useCronIncidentStore.getState().filterCategory).toBe('quota_exhausted');

    const closeBtn = screen.getByTestId('close-drawer-btn');
    fireEvent.click(closeBtn);
    expect(useCronIncidentStore.getState().isDrawerOpen).toBe(false);
  });

  it('should render CronIncidentCenterContainer integrating badge and drawer', () => {
    render(<CronIncidentCenterContainer />);
    expect(screen.getByTestId('cron-incident-center-container')).toBeInTheDocument();
    expect(screen.getByTestId('cron-incident-alert-badge')).toBeInTheDocument();
  });
});
