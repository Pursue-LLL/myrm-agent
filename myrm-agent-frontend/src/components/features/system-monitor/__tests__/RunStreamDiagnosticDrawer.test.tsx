import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RunStreamDiagnosticDrawer } from '../RunStreamDiagnosticDrawer';
import type {
  DiagnosticEventItem,
  DiagnosticStreamStatsData,
} from '../diagnosticStreamTypes';

describe('RunStreamDiagnosticDrawer', () => {
  const mockEvents: DiagnosticEventItem[] = [
    {
      event_id: 'diag_ev_01',
      session_id: 'sess_123',
      run_id: 'run_456',
      category: 'RETRY',
      severity: 'WARNING',
      code: 'DIAG_RETRY_BACKOFF',
      message: 'LLM 429 速率限制触发第 2 次重试，退避 1500ms',
      details: { attempt: '2', backoff_ms: '1500' },
      timestamp: '2026-10-12T14:00:00Z',
    },
    {
      event_id: 'diag_ev_02',
      session_id: 'sess_123',
      run_id: 'run_456',
      category: 'SANDBOX_PRESSURE',
      severity: 'CRITICAL',
      code: 'DIAG_SANDBOX_OOM',
      message: '沙箱内存占用突破 92% 告警阈值',
      details: { memory_pct: '92.4%' },
      timestamp: '2026-10-12T14:01:00Z',
    },
    {
      event_id: 'diag_ev_03',
      session_id: 'sess_123',
      run_id: 'run_456',
      category: 'CONTEXT_TRUNCATION',
      severity: 'INFO',
      code: 'DIAG_CTX_TRUNCATE',
      message: '上下文窗口接近上限，已滑窗剔除历史 8 轮',
      details: { evicted_turns: '8' },
      timestamp: '2026-10-12T14:02:00Z',
    },
  ];

  const mockStats: DiagnosticStreamStatsData = {
    total_events: 3,
    by_severity: {
      CRITICAL: 1,
      ERROR: 0,
      WARNING: 1,
      INFO: 1,
      DEBUG: 0,
    },
    by_category: {
      RETRY: 1,
      CONTEXT_TRUNCATION: 1,
      MCP_LATENCY: 0,
      SANDBOX_PRESSURE: 1,
      MODEL_DEGRADE: 0,
      CUSTOM: 0,
    },
  };

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <RunStreamDiagnosticDrawer
        isOpen={false}
        onClose={vi.fn()}
        events={mockEvents}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer with header, stats, and events when open', () => {
    const onClose = vi.fn();
    const onRefresh = vi.fn();

    render(
      <RunStreamDiagnosticDrawer
        isOpen={true}
        onClose={onClose}
        sessionId="sess_123"
        runId="run_456"
        events={mockEvents}
        stats={mockStats}
        onRefresh={onRefresh}
      />
    );

    // 头部与隔离说明
    expect(
      screen.getByText('运行流式诊断抽屉 (RunStream Diagnostics)')
    ).toBeInTheDocument();
    expect(screen.getByText('双轨解耦通道')).toBeInTheDocument();
    expect(
      screen.getByText(/物理隔离诊断事件流，杜绝内部重试、滑窗丢弃与沙箱压力混入普通聊天气泡/)
    ).toBeInTheDocument();

    // 会话与运行信息
    expect(screen.getByText('sess_123')).toBeInTheDocument();
    expect(screen.getByText('run_456')).toBeInTheDocument();

    // 统计数字
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('致命严重 (Critical)')).toBeInTheDocument();

    // 渲染事件卡片
    expect(screen.getByText('DIAG_RETRY_BACKOFF')).toBeInTheDocument();
    expect(screen.getByText('DIAG_SANDBOX_OOM')).toBeInTheDocument();
    expect(screen.getByText('DIAG_CTX_TRUNCATE')).toBeInTheDocument();
    expect(screen.getByText('attempt:')).toBeInTheDocument();
    expect(screen.getByText('1500')).toBeInTheDocument();

    // 点击刷新与关闭
    fireEvent.click(screen.getByText('刷新'));
    expect(onRefresh).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByLabelText('关闭诊断抽屉'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('filters events by severity tag correctly', () => {
    render(
      <RunStreamDiagnosticDrawer
        isOpen={true}
        onClose={vi.fn()}
        events={mockEvents}
      />
    );

    // 初始展示所有 3 个事件
    expect(screen.getByText('DIAG_RETRY_BACKOFF')).toBeInTheDocument();
    expect(screen.getByText('DIAG_SANDBOX_OOM')).toBeInTheDocument();
    expect(screen.getByText('DIAG_CTX_TRUNCATE')).toBeInTheDocument();

    // 点击 CRITICAL 过滤器
    const critBtn = screen.getByRole('button', { name: 'CRITICAL' });
    fireEvent.click(critBtn);

    // 此时仅有 DIAG_SANDBOX_OOM，其余应被过滤
    expect(screen.getByText('DIAG_SANDBOX_OOM')).toBeInTheDocument();
    expect(screen.queryByText('DIAG_RETRY_BACKOFF')).not.toBeInTheDocument();
    expect(screen.queryByText('DIAG_CTX_TRUNCATE')).not.toBeInTheDocument();
  });
});
