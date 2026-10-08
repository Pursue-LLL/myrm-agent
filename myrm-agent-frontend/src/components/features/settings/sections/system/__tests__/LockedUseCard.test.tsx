/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/LockedUseCard
 * - @/hooks/tauri/useTauri
 *
 * [OUTPUT]
 * - Test suite for the locked-use (screen unlock) settings card
 *
 * [POS]
 * Pins the opt-in switch contract: accessible switch semantics, disabled on platforms without
 * unlock support, and the next value reported through onToggle.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import LockedUseCard from '../LockedUseCard';

const mocks = vi.hoisted(() => ({
  invoke: vi.fn(),
  useTauri: vi.fn(),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/tauri/useTauri', () => ({
  useTauri: () => mocks.useTauri(),
}));

const supportFor = (unlock: boolean) =>
  Promise.resolve({ detection: true, unlock, keychain: unlock, platform: unlock ? 'macos' : 'linux' });

describe('LockedUseCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useTauri.mockReturnValue({ isTauri: true, invoke: mocks.invoke });
  });

  it('renders nothing outside the desktop shell', () => {
    mocks.useTauri.mockReturnValue({ isTauri: false, invoke: undefined });

    const { container } = render(<LockedUseCard enabled={false} onToggle={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('exposes an accessible switch and reports the next value when unlock is supported', async () => {
    mocks.invoke.mockImplementation((cmd: string) =>
      cmd === 'screen_lock_platform_support' ? supportFor(true) : Promise.resolve(false),
    );
    const onToggle = vi.fn();

    render(<LockedUseCard enabled={false} onToggle={onToggle} />);

    const toggle = screen.getByRole('switch', { name: 'layer2Title' });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(toggle);

    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('keeps the switch disabled when the platform cannot unlock', async () => {
    mocks.invoke.mockImplementation((cmd: string) =>
      cmd === 'screen_lock_platform_support' ? supportFor(false) : Promise.resolve(false),
    );
    const onToggle = vi.fn();

    render(<LockedUseCard enabled={false} onToggle={onToggle} />);

    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith('screen_lock_platform_support'));
    const toggle = screen.getByRole('switch', { name: 'layer2Title' });
    expect(toggle).toBeDisabled();

    fireEvent.click(toggle);

    expect(onToggle).not.toHaveBeenCalled();
  });
});
