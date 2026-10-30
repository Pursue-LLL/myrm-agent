/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const KNOWN_REASON_KEYS = new Set(['testReasons.TELEGRAM_TOKEN_REJECTED', 'testReasons.TELEGRAM_UNREACHABLE']);
const stableT = Object.assign((key: string) => key, { has: (key: string) => KNOWN_REASON_KEYS.has(key) });

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

import { toast } from 'sonner';
import { TelegramConfigCard } from '../TelegramConfigCard';

const SAVED = { botToken: '123:abc', botPolicy: 'deny', proxy: 'socks5://127.0.0.1:1080' };

describe('TelegramConfigCard', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
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

  it('does not let a proxy address without a supported scheme be saved', async () => {
    render(<TelegramConfigCard />);
    const proxy = await screen.findByLabelText('telegramProxy');
    const save = screen.getByRole('button', { name: /telegramSave/ });

    fireEvent.change(proxy, { target: { value: '127.0.0.1:7890' } });
    expect(save).toBeDisabled();

    fireEvent.change(proxy, { target: { value: 'http://127.0.0.1:7890' } });
    expect(save).toBeEnabled();
  });

  it('does not run a connection test through a proxy address without a supported scheme', async () => {
    render(<TelegramConfigCard />);
    const proxy = await screen.findByLabelText('telegramProxy');
    const test = screen.getByRole('button', { name: /telegramTestConnection/ });
    expect(test).toBeEnabled();

    fireEvent.change(proxy, { target: { value: '127.0.0.1:7890' } });
    expect(test).toBeDisabled();

    fireEvent.change(proxy, { target: { value: 'socks5://127.0.0.1:1080' } });
    expect(test).toBeEnabled();
  });

  describe('a failed connection check', () => {
    const SERVER_MESSAGE = 'English detail from the server';

    it.each([
      ['TELEGRAM_TOKEN_REJECTED', 'testReasons.TELEGRAM_TOKEN_REJECTED'],
      ['TELEGRAM_UNREACHABLE', 'testReasons.TELEGRAM_UNREACHABLE'],
      ['A_REASON_THE_PAGE_HAS_NO_TEXT_FOR', SERVER_MESSAGE],
      [undefined, SERVER_MESSAGE],
    ])('is explained for reason %s when the test button is used', async (reason, expectedToast) => {
      render(<TelegramConfigCard />);
      await waitFor(() => expect(mocks.testTelegramConnection).toHaveBeenCalledTimes(1));
      mocks.testTelegramConnection.mockResolvedValue({ ok: false, message: SERVER_MESSAGE, reason });

      fireEvent.click(screen.getByRole('button', { name: /telegramTestConnection/ }));

      await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expectedToast));
    });

    it('is explained in the same way when it follows a save', async () => {
      render(<TelegramConfigCard />);
      const proxy = await screen.findByLabelText('telegramProxy');
      await waitFor(() => expect(mocks.testTelegramConnection).toHaveBeenCalledTimes(1));
      mocks.testTelegramConnection.mockResolvedValue({
        ok: false,
        message: SERVER_MESSAGE,
        reason: 'TELEGRAM_UNREACHABLE',
      });

      fireEvent.change(proxy, { target: { value: 'http://127.0.0.1:7890' } });
      fireEvent.click(screen.getByRole('button', { name: /telegramSave/ }));

      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('testReasons.TELEGRAM_UNREACHABLE'));
    });
  });

  it('leaves the proxy to the hosted service in sandbox mode', async () => {
    mocks.sandbox = true;

    render(<TelegramConfigCard />);

    expect(await screen.findByLabelText('telegramBotToken')).toBeInTheDocument();
    expect(screen.queryByLabelText('telegramProxy')).not.toBeInTheDocument();
  });
});
