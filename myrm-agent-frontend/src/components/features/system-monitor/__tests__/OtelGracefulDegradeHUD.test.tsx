import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OtelGracefulDegradeHUD } from '../OtelGracefulDegradeHUD';
import type { OtelDegradeStatus } from '../otelDegradeTypes';

describe('OtelGracefulDegradeHUD', () => {
  const mockActiveStatus: OtelDegradeStatus = {
    state: 'ACTIVE',
    is_otel_installed: true,
    degrade_reason: null,
    intercepted_spans_count: 0,
    intercepted_metrics_count: 0,
    last_probe_time: '2026-10-12T12:00:00Z',
  };

  const mockDegradedStatus: OtelDegradeStatus = {
    state: 'DEGRADED_NO_OP',
    is_otel_installed: false,
    degrade_reason: "Dependency 'opentelemetry' is missing; gracefully degraded to No-Op",
    intercepted_spans_count: 48,
    intercepted_metrics_count: 120,
    last_probe_time: '2026-10-12T12:05:00Z',
  };

  it('renders ACTIVE status with installed badge and zero intercepted count', () => {
    const onProbe = vi.fn();
    render(<OtelGracefulDegradeHUD status={mockActiveStatus} onProbe={onProbe} />);

    expect(screen.getByText('OpenTelemetry 探针零硬依赖与优雅降级 HUD')).toBeInTheDocument();
    expect(screen.getByText('全量 OTel 追踪中 (Active)')).toBeInTheDocument();
    expect(screen.getByText('已检测到依赖包')).toBeInTheDocument();

    // 拦截计数为 0
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(2);

    // 主动自检按钮
    const probeBtn = screen.getByText('主动自检 (Probe)');
    fireEvent.click(probeBtn);
    expect(onProbe).toHaveBeenCalledTimes(1);
  });

  it('renders DEGRADED_NO_OP status with amber badge, degrade reason, and intercepted counters', async () => {
    const onToggle = vi.fn().mockResolvedValue(undefined);
    render(
      <OtelGracefulDegradeHUD
        status={mockDegradedStatus}
        onSimulateMissingToggle={onToggle}
      />
    );

    // 降级徽章与说明
    expect(
      screen.getByText('已优雅降级空跑 (Degraded No-Op) · 业务零中断')
    ).toBeInTheDocument();
    expect(screen.getByText('依赖缺失 · 安全隔离中')).toBeInTheDocument();

    // 拦截计数
    expect(screen.getByText('48')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();

    // 降级原因
    expect(
      screen.getByText(/Dependency 'opentelemetry' is missing/)
    ).toBeInTheDocument();

    // 还原依赖按钮交互
    const restoreBtn = screen.getByRole('button', { name: /还原依赖/ });
    expect(restoreBtn).toBeInTheDocument();
    fireEvent.click(restoreBtn);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  it('triggers simulation missing toggle when in ACTIVE state', async () => {
    const onToggle = vi.fn().mockResolvedValue(undefined);
    render(
      <OtelGracefulDegradeHUD
        status={mockActiveStatus}
        onSimulateMissingToggle={onToggle}
      />
    );

    const simBtn = screen.getByRole('button', { name: /模拟依赖缺失/ });
    expect(simBtn).toBeInTheDocument();
    fireEvent.click(simBtn);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle).toHaveBeenCalledWith(true);
  });
});
