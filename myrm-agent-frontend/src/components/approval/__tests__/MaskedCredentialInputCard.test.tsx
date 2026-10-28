import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MaskedCredentialInputCard } from '../MaskedCredentialInputCard';
import { OneTimeCredentialError } from '@/lib/approval/oneTimeCredentials';
import type { StagedCredentials } from '@/hooks/approval/useStagedCredentials';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

function stagedFor(seconds: number): StagedCredentials {
  return {
    items: [{ handleId: 'cred_ephemeral_xyz123abc456', key: 'TEST_API_KEY' }],
    expiresAtMs: Date.now() + seconds * 1000,
  };
}

const STAGED = stagedFor(45);

function renderCard(props: Partial<React.ComponentProps<typeof MaskedCredentialInputCard>> = {}) {
  const onStage = vi.fn().mockResolvedValue(undefined);
  const onRevoke = vi.fn().mockResolvedValue(undefined);
  render(<MaskedCredentialInputCard staged={null} onStage={onStage} onRevoke={onRevoke} {...props} />);
  return { onStage, onRevoke };
}

function fill(key: string, secret: string) {
  fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: key } });
  fireEvent.change(screen.getByPlaceholderText('••••••••••••'), { target: { value: secret } });
}

describe('MaskedCredentialInputCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the entry form with the single-use promise', () => {
    renderCard();

    expect(screen.getByText('title')).toBeDefined();
    expect(screen.getByText('badgeNeverSaved')).toBeDefined();
    expect(screen.getByText('singleUseEnforced')).toBeDefined();
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
    expect(screen.getByPlaceholderText('••••••••••••')).toBeDefined();
  });

  it('toggles password visibility between masked and text', () => {
    renderCard();

    const secretInput = screen.getByPlaceholderText('••••••••••••') as HTMLInputElement;
    expect(secretInput.type).toBe('password');

    const toggleButton = screen.getByRole('button', { name: 'showSecret' });
    expect(toggleButton).toBe(secretInput.nextElementSibling);
    fireEvent.click(toggleButton);

    expect(secretInput.type).toBe('text');
    expect(screen.getByRole('button', { name: 'hideSecret' })).toBe(toggleButton);
  });

  it('shows why a protected variable name cannot be used', () => {
    renderCard();

    fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'PATH' } });

    expect(screen.getByText('keyErrorBlocked:{"key":"PATH"}')).toBeDefined();
  });

  it('hands the normalised credentials to onStage and clears the typed secret', async () => {
    const { onStage } = renderCard();

    fill('test_api_key', 'super-sensitive-secret-token');
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(onStage).toHaveBeenCalledWith([
        { key: 'TEST_API_KEY', secret: 'super-sensitive-secret-token', ttlSeconds: 60 },
      ]);
    });
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('toastStaged'));
    expect((screen.getByPlaceholderText('••••••••••••') as HTMLInputElement).value).toBe('');
  });

  it('sends the lifetime the user picked', async () => {
    const { onStage } = renderCard();

    fill('TEST_API_KEY', 's');
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '300' } });
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(onStage).toHaveBeenCalledWith([{ key: 'TEST_API_KEY', secret: 's', ttlSeconds: 300 }]);
    });
  });

  it('shows what is staged with a countdown, never the secret or an internal id', () => {
    renderCard({ staged: stagedFor(45) });

    expect(screen.getByText('stagedReady')).toBeDefined();
    expect(screen.getByText('TEST_API_KEY')).toBeDefined();
    expect(screen.getByText('expiresIn:{"seconds":45}')).toBeDefined();
    expect(screen.queryByText(/cred_ephemeral/)).toBeNull();
    expect(screen.queryByPlaceholderText('API_SECRET_KEY')).toBeNull();
  });

  it('counts down while the credentials wait for approval', () => {
    vi.useFakeTimers();
    renderCard({ staged: stagedFor(45) });

    expect(screen.getByText('expiresIn:{"seconds":45}')).toBeDefined();
    act(() => vi.advanceTimersByTime(5_000));

    expect(screen.getByText('expiresIn:{"seconds":40}')).toBeDefined();
  });

  it('revokes through onRevoke and confirms', async () => {
    const { onRevoke } = renderCard({ staged: STAGED });

    fireEvent.click(screen.getByText('revoke'));

    await waitFor(() => expect(onRevoke).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toastMock.info).toHaveBeenCalledWith('toastCleared'));
  });

  it('tells the user when the credentials could not be destroyed, without echoing the failure', async () => {
    const { onRevoke } = renderCard({ staged: STAGED });
    onRevoke.mockRejectedValue(new TypeError('Failed to fetch'));

    fireEvent.click(screen.getByText('revoke'));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith('toastWipeFailed');
    });
    expect(toastMock.info).not.toHaveBeenCalled();
  });

  it('words a refused request as "check the input" and keeps the form', async () => {
    const { onStage } = renderCard();
    onStage.mockRejectedValue(new OneTimeCredentialError(400));

    fill('TEST_API_KEY', 'secret');
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith('toastStageFailed:{"message":"errorRejected"}');
    });
    expect(screen.getByPlaceholderText('API_SECRET_KEY')).toBeDefined();
  });

  it.each([
    ['a server error', new OneTimeCredentialError(503)],
    ['a network failure', new TypeError('Failed to fetch')],
  ])('words %s as "try again" without echoing it', async (_label, failure) => {
    const { onStage } = renderCard();
    onStage.mockRejectedValue(failure);

    fill('TEST_API_KEY', 'secret');
    fireEvent.click(screen.getByText('stage'));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith('toastStageFailed:{"message":"errorUnavailable"}');
    });
  });

  it('refuses a protected variable name before anything is sent', () => {
    const { onStage } = renderCard();

    fill('path', 'secret');
    fireEvent.click(screen.getByText('stage'));

    expect(toastMock.error).toHaveBeenCalledWith('keyErrorBlocked:{"key":"PATH"}');
    expect(onStage).not.toHaveBeenCalled();
  });

  it('asks for a value when only a name was typed', () => {
    const { onStage } = renderCard();

    fireEvent.change(screen.getByPlaceholderText('API_SECRET_KEY'), { target: { value: 'ONLY_NAME' } });

    expect(screen.getByText('stage').closest('button')?.hasAttribute('disabled')).toBe(true);
    expect(onStage).not.toHaveBeenCalled();
  });

  it('lets users remove an extra credential row through a labelled control', () => {
    renderCard();

    fireEvent.click(screen.getByText('addRow'));
    expect(screen.getAllByPlaceholderText('API_SECRET_KEY')).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('button', { name: 'removeCredential' })[0]);

    expect(screen.getAllByPlaceholderText('API_SECRET_KEY')).toHaveLength(1);
  });

  it('returns to an empty form once the staged credentials are gone', async () => {
    const onStage = vi.fn().mockResolvedValue(undefined);
    const onRevoke = vi.fn();
    const { rerender } = render(<MaskedCredentialInputCard staged={null} onStage={onStage} onRevoke={onRevoke} />);
    fill('TEST_API_KEY', 'secret');
    fireEvent.click(screen.getByText('stage'));
    await waitFor(() => expect(onStage).toHaveBeenCalled());

    rerender(<MaskedCredentialInputCard staged={STAGED} onStage={onStage} onRevoke={onRevoke} />);
    rerender(<MaskedCredentialInputCard staged={null} onStage={onStage} onRevoke={onRevoke} />);

    expect((screen.getByPlaceholderText('API_SECRET_KEY') as HTMLInputElement).value).toBe('');
    expect((screen.getByPlaceholderText('••••••••••••') as HTMLInputElement).value).toBe('');
  });
});
