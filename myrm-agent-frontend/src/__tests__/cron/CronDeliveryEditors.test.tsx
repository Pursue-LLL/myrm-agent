/**
 * 定时任务投递编辑器：除内置渠道外，任何已连接渠道都必须先填写收件人，保存时才提交。
 * 服务端对缺少收件人的 IM 渠道直接拒绝，因此编辑器不能在选中渠道时就提前保存。
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DeliveryEditor,
  FailureDeliveryEditor,
  IM_CHANNELS,
  needsDeliveryTarget,
} from '@/components/features/cron/CronDeliveryEditors';
import { listChannelStatuses } from '@/services/channels';
import type { ChannelStatus } from '@/services/channels';
import { updateCronJob } from '@/services/cron';
import type { CronJob } from '@/services/cron';

vi.mock('@/services/cron', () => ({
  updateCronJob: vi.fn(),
  testCronDelivery: vi.fn(),
}));
vi.mock('@/services/channels', () => ({
  listChannelStatuses: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const RECIPIENT = '+8613812345678';

const chatJob = { id: 'job-1', consecutive_failures: 0, delivery: { channel: 'chat' } } as CronJob;

function connect(...names: string[]): void {
  vi.mocked(listChannelStatuses).mockResolvedValue(names.map((name) => ({ name, status: 'running' }) as ChannelStatus));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(updateCronJob).mockResolvedValue(chatJob);
});

describe('needsDeliveryTarget 收件人判定', () => {
  it.each(['chat', 'webhook', 'none', 'web'])('内置渠道 %s 无需收件人', (channel) => {
    expect(needsDeliveryTarget(channel)).toBe(false);
  });

  it.each(Object.keys(IM_CHANNELS))('IM_CHANNELS 中的 %s 需要收件人', (channel) => {
    expect(needsDeliveryTarget(channel)).toBe(true);
  });

  it.each([
    'email',
    'signal',
    'line',
    'qq',
    'onebot',
    'wechat',
    'wechat_official',
    'wecom_aibot',
    'mattermost',
    'sms',
    'zalo',
    'imessage',
    'irc',
    'github',
  ])('服务端已注册的渠道 %s 同样需要收件人', (channel) => {
    expect(needsDeliveryTarget(channel)).toBe(true);
  });
});

describe('DeliveryEditor', () => {
  it('选中没有示例 ID 的渠道时只展示收件人输入框，填写后保存才提交', async () => {
    connect('signal');
    const user = userEvent.setup();
    render(<DeliveryEditor job={chatJob} onUpdated={vi.fn()} />);

    await user.click(await screen.findByRole('radio', { name: /signal/i }));

    expect(updateCronJob).not.toHaveBeenCalled();
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('placeholder', '');
    const save = screen.getByRole('button', { name: 'save' });
    expect(save).toBeDisabled();

    await user.type(input, RECIPIENT);
    await user.click(save);

    await waitFor(() =>
      expect(updateCronJob).toHaveBeenCalledWith('job-1', { delivery: { channel: 'signal', target: RECIPIENT } }),
    );
  });

  it('有示例 ID 的渠道保持原有行为：先填写收件人，且占位提示带示例', async () => {
    connect('telegram');
    const user = userEvent.setup();
    render(<DeliveryEditor job={chatJob} onUpdated={vi.fn()} />);

    await user.click(await screen.findByRole('radio', { name: /telegram/i }));

    expect(updateCronJob).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'imTargetPlaceholderRequired');
  });

  it('内置渠道无需收件人，选中即保存', async () => {
    connect('signal');
    const user = userEvent.setup();
    render(<DeliveryEditor job={chatJob} onUpdated={vi.fn()} />);

    await user.click(await screen.findByRole('radio', { name: 'deliveryNone' }));

    await waitFor(() => expect(updateCronJob).toHaveBeenCalledWith('job-1', { delivery: { channel: 'silent' } }));
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});

describe('FailureDeliveryEditor', () => {
  const failureJob = {
    ...chatJob,
    failure_delivery: { channel: 'webhook', target: 'https://alerts.example.com/hook' },
  } as CronJob;

  it('选中没有示例 ID 的渠道时展示收件人输入框，保存时一并提交收件人', async () => {
    connect('signal');
    const user = userEvent.setup();
    render(<FailureDeliveryEditor job={failureJob} onUpdated={vi.fn()} />);

    await user.click(await screen.findByRole('radio', { name: /signal/i }));

    const input = screen.getByRole('textbox');
    // The field starts out holding the stored webhook URL; an empty recipient must block saving.
    await user.clear(input);
    const save = screen.getByRole('button', { name: 'save' });
    expect(save).toBeDisabled();

    await user.type(input, RECIPIENT);
    await user.click(save);

    await waitFor(() =>
      expect(updateCronJob).toHaveBeenCalledWith('job-1', {
        failure_delivery: { channel: 'signal', target: RECIPIENT },
      }),
    );
  });
});
