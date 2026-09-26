import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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
  toast: { success: vi.fn(), error: vi.fn() },
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

describe('RecoveryGuideCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    vi.doMock('@tauri-apps/api/core', () => ({
      invoke: vi.fn(async (cmd: string) => {
        if (cmd === 'get_remote_follow') {
          return true;
        }
        throw new Error('unexpected command');
      }),
    }));
    const { tauriBackend } = await import('@/lib/tauri');
    const { toast } = await import('@/lib/utils/toast');
    render(<RecoveryGuideCard />);
    fireEvent.click(screen.getByText('retryBackend'));
    await waitFor(() => {
      expect(vi.mocked(toast.info)).toHaveBeenCalled();
    });
    expect(vi.mocked(tauriBackend.start)).not.toHaveBeenCalled();
    vi.doUnmock('@tauri-apps/api/core');
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
    handler?.({ payload: 'Port 8080 in use' });
    await waitFor(() => {
      expect(screen.getByText('Port 8080 in use')).toBeTruthy();
    });
  });
});
