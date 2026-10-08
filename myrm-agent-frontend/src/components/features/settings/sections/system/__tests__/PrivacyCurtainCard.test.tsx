/** @vitest-environment jsdom */
/**
 * [INPUT]
 * - @/components/features/settings/sections/system/PrivacyCurtainCard
 * - @/hooks/tauri/useTauri
 *
 * [OUTPUT]
 * - Unit test suite for the privacy curtain settings card
 *
 * [POS]
 * Verifies desktop-only rendering, active-state echo, engage/release IPC
 * routing and toast feedback for the manual curtain entry point.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PrivacyCurtainCard from '../PrivacyCurtainCard';

const stableT = (key: string) => key;
const invokeMock = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const useTauriMock = vi.fn();
vi.mock('@/hooks/tauri/useTauri', () => ({
  useTauri: () => useTauriMock(),
}));

import { toast } from '@/lib/utils/toast';

describe('PrivacyCurtainCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invokeMock.mockReset();
    invokeMock.mockResolvedValue(false);
  });

  it('renders nothing outside the desktop runtime', () => {
    useTauriMock.mockReturnValue({ isTauri: false, invoke: invokeMock });

    const { container } = render(<PrivacyCurtainCard enabled={false} onToggle={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it('echoes the inactive state on mount', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockResolvedValue(false);

    render(<PrivacyCurtainCard enabled={false} onToggle={vi.fn()} />);

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('privacy_curtain_active'));
    expect(await screen.findByText('inactiveBadge')).toBeInTheDocument();
    expect(screen.getByText('engage')).toBeInTheDocument();
  });

  it('shows the active badge and release action when the curtain is up', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockResolvedValue(true);

    render(<PrivacyCurtainCard enabled onToggle={vi.fn()} />);

    expect(await screen.findByText('activeBadge')).toBeInTheDocument();
    expect(screen.getByText('release')).toBeInTheDocument();
  });

  it('engages the curtain and reports success', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockResolvedValue(false);

    render(<PrivacyCurtainCard enabled onToggle={vi.fn()} />);
    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('privacy_curtain_active'));

    fireEvent.click(screen.getByText('engage'));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('show_privacy_curtain'));
    expect(toast.success).toHaveBeenCalledWith('toastEngaged');
    expect(await screen.findByText('activeBadge')).toBeInTheDocument();
  });

  it('releases the curtain and reports success', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockResolvedValue(true);

    render(<PrivacyCurtainCard enabled onToggle={vi.fn()} />);
    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('privacy_curtain_active'));

    fireEvent.click(screen.getByText('release'));

    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('hide_privacy_curtain'));
    expect(toast.success).toHaveBeenCalledWith('toastReleased');
    expect(await screen.findByText('inactiveBadge')).toBeInTheDocument();
  });

  it('reports an error when engaging fails', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'show_privacy_curtain' ? Promise.reject(new Error('boom')) : Promise.resolve(false),
    );

    render(<PrivacyCurtainCard enabled onToggle={vi.fn()} />);
    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('privacy_curtain_active'));

    fireEvent.click(screen.getByText('engage'));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(screen.getByText('engage')).toBeInTheDocument();
  });

  it('forwards the toggled value to the parent', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    const onToggle = vi.fn();

    render(<PrivacyCurtainCard enabled={false} onToggle={onToggle} />);
    await waitFor(() => expect(invokeMock).toHaveBeenCalledWith('privacy_curtain_active'));

    const toggle = screen.getByRole('switch', { name: 'autoTitle' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(toggle);

    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('survives an active-state echo failure without breaking the card', async () => {
    useTauriMock.mockReturnValue({ isTauri: true, invoke: invokeMock });
    invokeMock.mockRejectedValue(new Error('bridge down'));

    render(<PrivacyCurtainCard enabled onToggle={vi.fn()} />);

    expect(await screen.findByText('autoTitle')).toBeInTheDocument();
    expect(await screen.findByText('inactiveBadge')).toBeInTheDocument();
  });
});
