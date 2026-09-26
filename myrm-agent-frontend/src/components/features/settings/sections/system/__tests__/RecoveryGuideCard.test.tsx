import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import RecoveryGuideCard from '../RecoveryGuideCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconAlertCircle: () => <span data-testid="icon-fail" />,
  IconWrench: () => <span data-testid="icon-wrench" />,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

vi.mock('@/lib/tauri', () => ({
  tauriBackend: { start: vi.fn(async () => 'Backend started and healthy') },
}));

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(async () => () => undefined),
}));

const mockInvoke = vi.fn();

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

describe('RecoveryGuideCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (window as unknown as { __TAURI_INTERNALS__: { invoke: typeof mockInvoke } }).__TAURI_INTERNALS__ = {
      invoke: mockInvoke,
    };
    mockInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === 'get_backend_status') {
        return 'running';
      }
      if (cmd === 'get_remote_follow') {
        return false;
      }
      return undefined;
    });
  });

  afterEach(() => {
    delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  });

  it('renders non-destructive recovery actions', () => {
    render(<RecoveryGuideCard />);
    expect(screen.getByText('description')).toBeTruthy();
    expect(screen.getByText('retryBackend')).toBeTruthy();
    expect(screen.getByText('reinstall')).toBeTruthy();
    expect(screen.getByText('dataSafeHint')).toBeTruthy();
  });

  it('retries backend start without touching data', async () => {
    const { tauriBackend } = await import('@/lib/tauri');
    render(<RecoveryGuideCard />);
    fireEvent.click(screen.getByText('retryBackend'));
    await waitFor(() => {
      expect(vi.mocked(tauriBackend.start)).toHaveBeenCalledTimes(1);
    });
  });

  it('skips local restart while remote follow is active', async () => {
    mockInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === 'get_remote_follow') {
        return true;
      }
      if (cmd === 'get_backend_status') {
        return 'running';
      }
      return undefined;
    });
    const { tauriBackend } = await import('@/lib/tauri');
    const { toast } = await import('@/lib/utils/toast');
    render(<RecoveryGuideCard />);
    fireEvent.click(screen.getByText('retryBackend'));
    await waitFor(() => {
      expect(vi.mocked(toast.info)).toHaveBeenCalled();
    });
    expect(vi.mocked(tauriBackend.start)).not.toHaveBeenCalled();
  });

  it('surfaces failure events when they arrive', async () => {
    const { listen } = await import('@tauri-apps/api/event');
    let handler: ((e: { payload: unknown }) => void) | null = null;
    vi.mocked(listen).mockImplementation(async (event: string, cb: never) => {
      if (event === 'backend-start-failed') {
        handler = cb as unknown as (e: { payload: unknown }) => void;
      }
      return () => undefined;
    });
    render(<RecoveryGuideCard />);
    await waitFor(() => {
      expect(handler).not.toBeNull();
    });
    act(() => {
      handler?.({ payload: 'Port 8080 in use' });
    });
    await waitFor(() => {
      expect(screen.getByText('Port 8080 in use')).toBeTruthy();
    });
  });
});
