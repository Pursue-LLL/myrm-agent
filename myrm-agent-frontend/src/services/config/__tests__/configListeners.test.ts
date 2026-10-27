import { describe, expect, it, vi } from 'vitest';
import { ConfigListenerRegistry } from '@/services/config/configListeners';

const meta = { version: '1000_0', updatedAt: '2026-01-01T00:00:00.000Z', deviceId: 'dev' };

describe('ConfigListenerRegistry', () => {
  it('delivers a change to every subscriber of that key only', () => {
    const registry = new ConfigListenerRegistry();
    const chat = vi.fn();
    const personal = vi.fn();
    registry.subscribe('chatSettings', chat);
    registry.subscribe('personalSettings', personal);

    registry.notify('chatSettings', {} as never, meta);

    expect(chat).toHaveBeenCalledWith('chatSettings', {}, meta);
    expect(personal).not.toHaveBeenCalled();
  });

  it('keeps delivering when one subscriber throws', () => {
    const registry = new ConfigListenerRegistry();
    const later = vi.fn();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    registry.subscribe('chatSettings', () => {
      throw new Error('broken subscriber');
    });
    registry.subscribe('chatSettings', later);

    registry.notify('chatSettings', {} as never, meta);

    expect(later).toHaveBeenCalledTimes(1);
  });

  it('stops delivering after the returned unsubscribe is called', () => {
    const registry = new ConfigListenerRegistry();
    const listener = vi.fn();
    const unsubscribe = registry.subscribe('chatSettings', listener);

    unsubscribe();
    registry.notify('chatSettings', {} as never, meta);

    expect(listener).not.toHaveBeenCalled();
  });
});
