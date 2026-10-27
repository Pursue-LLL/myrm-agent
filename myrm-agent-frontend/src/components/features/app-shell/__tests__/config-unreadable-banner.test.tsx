import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConfigKey } from '@/services/config/types';
import ConfigUnreadableBanner from '../config-unreadable-banner';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string) => `${namespace}.${key}`,
}));

const manager = vi.hoisted(() => ({
  unreadable: [] as ConfigKey[],
  listeners: new Map<ConfigKey, () => void>(),
  unsubscribe: vi.fn(),
  initialize: vi.fn(() => Promise.resolve(new Map())),
  getUnreadableKeys: vi.fn(),
  subscribe: vi.fn(),
}));

vi.mock('@/services/config/ConfigSyncManager', () => ({
  getConfigSyncManager: () => manager,
}));

const renderBanner = async () => {
  const view = render(<ConfigUnreadableBanner />);
  await act(async () => {
    await Promise.resolve();
  });
  return view;
};

describe('ConfigUnreadableBanner', () => {
  beforeEach(() => {
    manager.unreadable = [];
    manager.listeners.clear();
    manager.unsubscribe.mockClear();
    manager.getUnreadableKeys.mockImplementation(() => [...manager.unreadable]);
    manager.subscribe.mockImplementation((key: ConfigKey, listener: () => void) => {
      manager.listeners.set(key, listener);
      return manager.unsubscribe;
    });
  });

  it('shows nothing when every saved config can be read', async () => {
    await renderBanner();

    expect(screen.queryByTestId('config-unreadable-banner')).toBeNull();
  });

  it('tells the user which kind of problem it is when a saved config cannot be read', async () => {
    manager.unreadable = ['providers'];

    await renderBanner();

    expect(screen.getByTestId('config-unreadable-banner')).toBeTruthy();
    expect(screen.getByText('common.configUnreadable.title')).toBeTruthy();
    expect(screen.getByText('common.configUnreadable.description')).toBeTruthy();
  });

  it('goes away once the user saves the config and it is no longer unreadable', async () => {
    manager.unreadable = ['providers'];
    await renderBanner();

    manager.unreadable = [];
    act(() => manager.listeners.get('providers')?.());

    expect(screen.queryByTestId('config-unreadable-banner')).toBeNull();
  });

  it('can be dismissed', async () => {
    manager.unreadable = ['providers'];
    await renderBanner();

    fireEvent.click(screen.getByLabelText('common.close'));

    expect(screen.queryByTestId('config-unreadable-banner')).toBeNull();
  });

  it('stops listening when it unmounts', async () => {
    manager.unreadable = ['providers'];
    const view = await renderBanner();

    view.unmount();

    expect(manager.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
