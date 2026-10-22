import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { RuntimeCodeFreshnessHUD } from '../RuntimeCodeFreshnessHUD';
import { RuntimeFreshnessReportItem } from '../codeFreshnessTypes';

describe('RuntimeCodeFreshnessHUD Component', () => {
  const mockReport: RuntimeFreshnessReportItem = {
    pid: 8848,
    overall_state: 'stale',
    total_inspected_modules: 3,
    stale_modules_count: 1,
    fresh_modules_count: 1,
    indeterminate_count: 1,
    inspected_at_ms: 1791806400000,
    details: [
      {
        module_name: 'app.api.router',
        file_path: '/app/api/router.py',
        process_start_time_ms: 1791800000000,
        disk_mtime_ms: 1791790000000,
        time_drift_seconds: -10.0,
        state: 'fresh',
        reason: 'none',
        remediation_hint: 'Runtime in-memory bytecode matches current disk version.',
      },
      {
        module_name: 'app.services.gateway',
        file_path: '/app/services/gateway.py',
        process_start_time_ms: 1791800000000,
        disk_mtime_ms: 1791801800000,
        time_drift_seconds: 18.0,
        state: 'stale',
        reason: 'none',
        remediation_hint: 'Process is 18.0s older than disk code. Gracefully drain active sessions and reload process.',
      },
      {
        module_name: 'ghost_module',
        file_path: '/missing/file.py',
        process_start_time_ms: 1791800000000,
        disk_mtime_ms: null,
        time_drift_seconds: null,
        state: 'indeterminate',
        reason: 'file_not_found',
        remediation_hint: 'File path not found on disk; verify repository installation.',
      },
    ],
  };

  it('renders overall status, KPI totals, and module table', () => {
    render(<RuntimeCodeFreshnessHUD report={mockReport} />);

    expect(screen.getByTestId('runtime-code-freshness-hud')).toBeInTheDocument();
    expect(screen.getByText(/存在旧代码静默执行/)).toBeInTheDocument();
    expect(screen.getByText('PID: 8848')).toBeInTheDocument();
    expect(screen.getByText('3 个')).toBeInTheDocument();
    expect(screen.getAllByText('app.api.router').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('app.services.gateway').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('ghost_module').length).toBeGreaterThanOrEqual(1);
  });

  it('filters module list by freshness state', async () => {
    render(<RuntimeCodeFreshnessHUD report={mockReport} />);

    // Click 'STALE' filter
    const filterStale = screen.getByTestId('filter-stale');
    await act(async () => {
      fireEvent.click(filterStale);
    });

    expect(screen.getByText('app.services.gateway')).toBeInTheDocument();
    expect(screen.queryByText('app.api.router')).not.toBeInTheDocument();

    // Click 'ALL' filter back
    const filterAll = screen.getByTestId('filter-all');
    await act(async () => {
      fireEvent.click(filterAll);
    });

    expect(screen.getByText('app.api.router')).toBeInTheDocument();
  });

  it('handles recheck trigger and custom module inspection', async () => {
    const handleRecheck = vi.fn().mockResolvedValue(undefined);
    const handleInspectModule = vi.fn().mockResolvedValue(undefined);

    render(
      <RuntimeCodeFreshnessHUD
        report={mockReport}
        onRecheck={handleRecheck}
        onInspectModule={handleInspectModule}
      />
    );

    // Recheck
    const btnRecheck = screen.getByTestId('btn-recheck-freshness');
    await act(async () => {
      fireEvent.click(btnRecheck);
    });
    expect(handleRecheck).toHaveBeenCalledTimes(1);

    // Custom inspect
    const inputName = screen.getByTestId('input-custom-module-name');
    const inputPath = screen.getByTestId('input-custom-module-path');
    const btnInspect = screen.getByTestId('btn-inspect-custom');

    await act(async () => {
      fireEvent.change(inputName, { target: { value: 'custom.test' } });
      fireEvent.change(inputPath, { target: { value: '/tmp/test.py' } });
      fireEvent.click(btnInspect);
    });

    expect(handleInspectModule).toHaveBeenCalledWith('custom.test', '/tmp/test.py');
  });
});
