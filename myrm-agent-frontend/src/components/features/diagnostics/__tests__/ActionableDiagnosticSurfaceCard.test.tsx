import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ActionableDiagnosticSurfaceCard } from '../ActionableDiagnosticSurfaceCard';
import { useStderrDiagnosticStore } from '../useStderrDiagnosticStore';

describe('ActionableDiagnosticSurfaceCard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    act(() => {
      useStderrDiagnosticStore.getState().resetDiagnosticState();
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when activeDiagnostic is null', () => {
    const { container } = render(<ActionableDiagnosticSurfaceCard />);
    expect(container.firstChild).toBeNull();
  });

  it('renders diagnostic card with exit cause and root cause summary', () => {
    act(() => {
      useStderrDiagnosticStore.getState().ingestStderrChunk('Killed: Out of memory\n');
      useStderrDiagnosticStore.getState().classifyProcessExit(137);
    });

    render(<ActionableDiagnosticSurfaceCard />);

    expect(screen.getByRole('region', { name: '进程退出因果诊断与可操作排障向导' })).toBeInTheDocument();
    expect(screen.getByText('沙箱内存耗尽 (OOM Killed)')).toBeInTheDocument();
    expect(screen.getByText('Exit Code 137')).toBeInTheDocument();
    expect(screen.getByText('敏感路径与令牌已脱敏')).toBeInTheDocument();
    expect(screen.getByText(/触发了宿主沙箱内存硬限制/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '将沙箱内存提升至 4GB' })).toBeInTheDocument();
  });

  it('toggles raw stderr snippet view', () => {
    act(() => {
      useStderrDiagnosticStore.getState().ingestStderrChunk('Error snippet tail details\n');
      useStderrDiagnosticStore.getState().classifyProcessExit(1);
    });

    render(<ActionableDiagnosticSurfaceCard />);

    const toggleBtn = screen.getByRole('button', { name: '展开或收起受限脱敏 Stderr 尾部' });
    expect(screen.queryByText(/TERMINAL STDERR BOUNDED TAIL/i)).not.toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.getByText(/TERMINAL STDERR BOUNDED TAIL/i)).toBeInTheDocument();

    fireEvent.click(toggleBtn);
    expect(screen.queryByText(/TERMINAL STDERR BOUNDED TAIL/i)).not.toBeInTheDocument();
  });

  it('executes fix action and displays success message', async () => {
    act(() => {
      useStderrDiagnosticStore.getState().ingestStderrChunk('Killed\n');
      useStderrDiagnosticStore.getState().classifyProcessExit(137);
    });

    render(<ActionableDiagnosticSurfaceCard />);

    const fixBtn = screen.getByRole('button', { name: '将沙箱内存提升至 4GB' });
    fireEvent.click(fixBtn);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    expect(screen.getByText('沙箱运行内存已成功扩容至 4GB，硬件限制已重置！')).toBeInTheDocument();
  });

  it('dismisses card when close button is clicked', () => {
    act(() => {
      useStderrDiagnosticStore.getState().ingestStderrChunk('Fatal error\n');
      useStderrDiagnosticStore.getState().classifyProcessExit(1);
    });

    render(<ActionableDiagnosticSurfaceCard />);

    const closeBtn = screen.getByRole('button', { name: '关闭诊断卡片' });
    fireEvent.click(closeBtn);

    expect(useStderrDiagnosticStore.getState().activeDiagnostic).toBeNull();
  });
});
