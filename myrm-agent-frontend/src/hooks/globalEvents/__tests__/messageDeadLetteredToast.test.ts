import { describe, expect, it, vi } from 'vitest';

import { showMessageDeadLetteredToast } from '@/hooks/globalEvents/messageDeadLetteredToast';

const toastMocks = vi.hoisted(() => ({
  error: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: toastMocks,
}));

describe('showMessageDeadLetteredToast', () => {
  const t = (key: string, values?: Record<string, string | number>) =>
    values ? `${key}:${JSON.stringify(values)}` : key;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows error toast with channel and reason', () => {
    const notifyIfLeader = vi.fn();
    const dispatchEvent = vi.fn();

    showMessageDeadLetteredToast(
      { channel: 'telegram', error_reason: 'timeout after 3 retries' },
      { t, notifyIfLeader, dispatchEvent },
    );

    expect(toastMocks.error).toHaveBeenCalledOnce();
    expect(toastMocks.error).toHaveBeenCalledWith(
      'messageDeadLettered:{"channel":"telegram","reason":"timeout after 3 retries"}',
      expect.objectContaining({ duration: 10_000, dismissible: true }),
    );
    expect(notifyIfLeader).toHaveBeenCalledWith(
      'messageDeadLettered:{"channel":"telegram","reason":"timeout after 3 retries"}',
      'timeout after 3 retries',
    );
    expect(dispatchEvent).toHaveBeenCalledWith('message_dead_lettered');
  });

  it('defaults missing fields to unknown / Unknown error', () => {
    const notifyIfLeader = vi.fn();
    const dispatchEvent = vi.fn();

    showMessageDeadLetteredToast({}, { t, notifyIfLeader, dispatchEvent });

    expect(toastMocks.error).toHaveBeenCalledWith(
      'messageDeadLettered:{"channel":"unknown","reason":"Unknown error"}',
      expect.any(Object),
    );
    expect(notifyIfLeader).toHaveBeenCalledWith(
      'messageDeadLettered:{"channel":"unknown","reason":"Unknown error"}',
      'Unknown error',
    );
  });

  it('dispatches window event when dispatchEvent is omitted', () => {
    const handler = vi.fn();
    window.addEventListener('message_dead_lettered', handler);

    showMessageDeadLetteredToast(
      { channel: 'chat', error_reason: 'orm write failed' },
      { t, notifyIfLeader: vi.fn() },
    );

    expect(handler).toHaveBeenCalledOnce();
    window.removeEventListener('message_dead_lettered', handler);
  });
});
