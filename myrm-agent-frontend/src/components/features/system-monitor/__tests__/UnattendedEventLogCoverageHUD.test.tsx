import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { UnattendedEventLogCoverageHUD } from '../UnattendedEventLogCoverageHUD';
import type { CoverageSummaryResponse, ValidateSessionIdResponse } from '../unattendedCoverageTypes';

describe('UnattendedEventLogCoverageHUD Component', () => {
  const mockSummary: CoverageSummaryResponse = {
    event_log_dir: '/Users/test/.myrm/event_logs',
    max_line_bytes: 102400,
    is_directory_configured: true,
    anti_growth_protection: true,
    entrypoints: [
      {
        entrypoint: 'cron',
        is_injected: true,
        strategy_desc: '独立运行按日分片 (cron:{job_id}:{date})，主会话复用 chat_id',
        sample_session_id: 'cron:nightly_backup:2026-10-13',
        is_safe: true,
      },
      {
        entrypoint: 'channel',
        is_injected: true,
        strategy_desc: '安全白名单清洗与渠道前缀绑定 (channel_{name}:{id})',
        sample_session_id: 'channel_telegram:tg_group_987',
        is_safe: true,
      },
      {
        entrypoint: 'goal',
        is_injected: true,
        strategy_desc: '目标会话透传与安全隔离 (goal:{id})',
        sample_session_id: 'goal:autonomous_audit',
        is_safe: true,
      },
      {
        entrypoint: 'voice',
        is_injected: true,
        strategy_desc: '语音 Bridge 规范前缀与安全会话透传',
        sample_session_id: 'voice:chat_session_001',
        is_safe: true,
      },
      {
        entrypoint: 'voice_realtime',
        is_injected: true,
        strategy_desc: '实时工具执行按日分片 (voice:realtime:{date})，防单文件无限追加',
        sample_session_id: 'voice:realtime:2026-10-13',
        is_safe: true,
      },
      {
        entrypoint: 'web_chat',
        is_injected: true,
        strategy_desc: '对话入口原生注入与安全校验',
        sample_session_id: 'chat-123e4567-e89b',
        is_safe: true,
      },
    ],
    shards: [
      { prefix: 'cron', file_count: 5, total_bytes: 20480 },
      { prefix: 'channel', file_count: 2, total_bytes: 8192 },
      { prefix: 'web', file_count: 12, total_bytes: 65536 },
    ],
  };

  it('renders summary cards, badges, and all entrypoint rows', () => {
    render(<UnattendedEventLogCoverageHUD summary={mockSummary} />);

    expect(screen.getByTestId('hud-unattended-coverage')).toBeInTheDocument();
    expect(screen.getByTestId('anti-growth-badge')).toHaveTextContent('防无限增长保护已激活');
    expect(screen.getByTestId('dir-status')).toHaveTextContent('已配置就绪');

    expect(screen.getByTestId('entrypoint-cron')).toBeInTheDocument();
    expect(screen.getByTestId('entrypoint-channel')).toBeInTheDocument();
    expect(screen.getByTestId('entrypoint-goal')).toBeInTheDocument();
    expect(screen.getByTestId('entrypoint-voice')).toBeInTheDocument();
    expect(screen.getByTestId('entrypoint-voice_realtime')).toBeInTheDocument();
    expect(screen.getByTestId('entrypoint-web_chat')).toBeInTheDocument();

    expect(screen.getByText('cron:nightly_backup:2026-10-13')).toBeInTheDocument();
  });

  it('handles refresh button callback', () => {
    const handleRefresh = vi.fn();
    render(<UnattendedEventLogCoverageHUD summary={mockSummary} onRefresh={handleRefresh} />);

    const refreshBtn = screen.getByTestId('btn-refresh');
    fireEvent.click(refreshBtn);
    expect(handleRefresh).toHaveBeenCalledTimes(1);
  });

  it('executes validate callback and displays parsed result', async () => {
    const mockValidateResult: ValidateSessionIdResponse = {
      entrypoint: 'cron',
      resolved_session_id: 'cron:test_job_123:2026-10-13',
      is_safe: true,
      is_daily_sharded: true,
    };
    const handleValidate = vi.fn().mockResolvedValue(mockValidateResult);

    render(<UnattendedEventLogCoverageHUD summary={mockSummary} onValidate={handleValidate} />);

    const input = screen.getByTestId('input-identifier');
    fireEvent.change(input, { target: { value: 'test_job_123' } });

    const validateBtn = screen.getByTestId('btn-validate');
    fireEvent.click(validateBtn);

    await waitFor(() => {
      expect(handleValidate).toHaveBeenCalledWith('cron', 'test_job_123');
    });

    await waitFor(() => {
      expect(screen.getByTestId('validation-result')).toBeInTheDocument();
      expect(screen.getByText('cron:test_job_123:2026-10-13')).toBeInTheDocument();
      expect(screen.getByText(/安全通过 \(Safe\)/)).toBeInTheDocument();
      expect(screen.getByText(/已分片 \(Daily Sharded\)/)).toBeInTheDocument();
    });
  });
});
