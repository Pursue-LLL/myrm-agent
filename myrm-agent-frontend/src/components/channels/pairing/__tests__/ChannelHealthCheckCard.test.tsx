import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { ChannelHealthCheckCard } from '../ChannelHealthCheckCard';
import { ChannelPairingService } from '../channelPairingService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '连通性自测与时延探测',
    modelAgnostic: '确定性传输',
    description: '通过系统级直连向目标通道发送探测消息，毫秒级验证推送通路与回执状态。',
    targetLabel: '接收者/会话标识（可选）',
    targetPlaceholder: '留空使用配对默认用户',
    messageLabel: '测试探测内容',
    sendPing: '发送测试消息',
    latency: '往返延迟:',
    successTitle: '连通性验证成功',
    receiptLabel: '回执单号:',
    errorTitle: '连通性测试未通过',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ChannelHealthCheckCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders initial state with title and ping button', () => {
    render(<ChannelHealthCheckCard platform="wechat" />);

    expect(screen.getByTestId('channel-health-check-card')).toBeInTheDocument();
    expect(screen.getByTestId('send-ping-button')).toBeInTheDocument();
    expect(screen.getByText('连通性自测与时延探测')).toBeInTheDocument();
    expect(screen.getByText('确定性传输')).toBeInTheDocument();
  });

  it('sends ping successfully and displays latency and receipt ID', async () => {
    const mockVerified = vi.fn();
    vi.spyOn(ChannelPairingService, 'verifyChannelPing').mockResolvedValueOnce({
      platform: 'wechat',
      success: true,
      latency_ms: 36.4,
      receipt_id: 'rcpt_test_123456',
      dispatched_at_epoch_ms: 1700000000,
      error_detail: null,
    });

    render(<ChannelHealthCheckCard platform="wechat" defaultRecipient="wx_user_99" onVerified={mockVerified} />);

    const pingBtn = screen.getByTestId('send-ping-button');

    await act(async () => {
      fireEvent.click(pingBtn);
    });

    expect(ChannelPairingService.verifyChannelPing).toHaveBeenCalledWith({
      platform: 'wechat',
      target_recipient: 'wx_user_99',
      test_message: '[Myrm Ping] Model-agnostic channel verification.',
    });

    expect(mockVerified).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('ping-success-banner')).toBeInTheDocument();
    expect(screen.getByText('36.4 ms')).toBeInTheDocument();
    expect(screen.getByText('rcpt_test_123456')).toBeInTheDocument();
  });

  it('handles error gracefully when ping fails', async () => {
    vi.spyOn(ChannelPairingService, 'verifyChannelPing').mockRejectedValueOnce(
      new Error('Network timeout connecting to channel gateway'),
    );

    render(<ChannelHealthCheckCard platform="dingtalk" />);

    const pingBtn = screen.getByTestId('send-ping-button');

    await act(async () => {
      fireEvent.click(pingBtn);
    });

    expect(screen.getByTestId('ping-error-banner')).toBeInTheDocument();
    expect(screen.getByText('Network timeout connecting to channel gateway')).toBeInTheDocument();
  });
});
