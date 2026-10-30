/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mocks = vi.hoisted(() => ({
  sandbox: false,
  getTelegramCredentials: vi.fn(),
  saveTelegramCredentials: vi.fn(),
  testTelegramConnection: vi.fn(),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, isSandbox: () => mocks.sandbox };
});

vi.mock('@/services/channels', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getTelegramCredentials: (...args: unknown[]) => mocks.getTelegramCredentials(...args),
    saveTelegramCredentials: (...args: unknown[]) => mocks.saveTelegramCredentials(...args),
    testTelegramConnection: (...args: unknown[]) => mocks.testTelegramConnection(...args),
  };
});

vi.mock('../CpInboundUrlBanner', () => ({ CpInboundUrlBanner: () => null }));

import { TelegramConfigCard } from '../TelegramConfigCard';

const SAVED = { botToken: '123:abc', botPolicy: 'deny', proxy: 'socks5://127.0.0.1:1080' };

describe('TelegramConfigCard', () => {
  beforeEach(() => {
    mocks.sandbox = false;
    mocks.getTelegramCredentials.mockReset().mockResolvedValue(SAVED);
    mocks.saveTelegramCredentials.mockReset().mockResolvedValue(undefined);
    mocks.testTelegramConnection.mockReset().mockResolvedValue({ ok: true });
  });

  it('shows the saved proxy and checks the connection through it', async () => {
    render(<TelegramConfigCard />);

    expect(await screen.findByLabelText('telegramProxy')).toHaveValue('socks5://127.0.0.1:1080');
    await waitFor(() =>
      expect(mocks.testTelegramConnection).toHaveBeenCalledWith('123:abc', 'socks5://127.0.0.1:1080'),
    );
  });

  it('tests and saves the proxy the user typed', async () => {
    render(<TelegramConfigCard />);
    const proxy = await screen.findByLabelText('telegramProxy');
    await waitFor(() => expect(mocks.testTelegramConnection).toHaveBeenCalledTimes(1));

    fireEvent.change(proxy, { target: { value: 'http://127.0.0.1:7890' } });
    fireEvent.click(screen.getByRole('button', { name: /telegramTestConnection/ }));
    await waitFor(() =>
      expect(mocks.testTelegramConnection).toHaveBeenLastCalledWith('123:abc', 'http://127.0.0.1:7890'),
    );

    fireEvent.click(screen.getByRole('button', { name: /telegramSave/ }));
    await waitFor(() =>
      expect(mocks.saveTelegramCredentials).toHaveBeenCalledWith(
        expect.objectContaining({ proxy: 'http://127.0.0.1:7890' }),
      ),
    );
  });

  it('points out a proxy address that lacks a supported scheme', async () => {
    render(<TelegramConfigCard />);
    const proxy = await screen.findByLabelText('telegramProxy');
    expect(screen.queryByText('telegramProxyInvalid')).not.toBeInTheDocument();

    fireEvent.change(proxy, { target: { value: '127.0.0.1:7890' } });
    expect(screen.getByText('telegramProxyInvalid')).toBeInTheDocument();

    fireEvent.change(proxy, { target: { value: ' socks5h://127.0.0.1:1080 ' } });
    expect(screen.queryByText('telegramProxyInvalid')).not.toBeInTheDocument();

    fireEvent.change(proxy, { target: { value: '' } });
    expect(screen.queryByText('telegramProxyInvalid')).not.toBeInTheDocument();
  });

  it('leaves the proxy to the hosted service in sandbox mode', async () => {
    mocks.sandbox = true;

    render(<TelegramConfigCard />);

    expect(await screen.findByLabelText('telegramBotToken')).toBeInTheDocument();
    expect(screen.queryByLabelText('telegramProxy')).not.toBeInTheDocument();
  });
});
