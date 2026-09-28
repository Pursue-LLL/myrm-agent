import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ResourcePressureBanner from '../ResourcePressureBanner';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconAlertCircle: () => <span data-testid="icon-alert" />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}));

describe('ResourcePressureBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.useRealTimers();
  });

  function mockPressure(payload: object) {
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => payload,
    })) as unknown as typeof fetch;
  }

  it('shows disk-critical first (worst-first ordering)', async () => {
    mockPressure({ memory: { level: 'critical' }, disk: { state: 'critical' } });
    render(<ResourcePressureBanner />);
    await waitFor(() => {
      expect(screen.getByText('trigger.disk_critical.title')).toBeTruthy();
    });
  });

  it('shows memory-critical when disk is fine', async () => {
    mockPressure({ memory: { level: 'emergency' }, disk: { state: 'ok' } });
    render(<ResourcePressureBanner />);
    await waitFor(() => {
      expect(screen.getByText('trigger.memory_critical.title')).toBeTruthy();
    });
  });

  it('stays silent when everything is ok', async () => {
    mockPressure({ memory: { level: 'normal' }, disk: { state: 'ok' } });
    const { container } = render(<ResourcePressureBanner />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(container.firstChild).toBeNull();
  });

  it('dismisses per session and re-opens on escalation', async () => {
    mockPressure({ memory: { level: 'warning' }, disk: { state: 'ok' } });
    const { unmount } = render(<ResourcePressureBanner />);
    await waitFor(() => {
      expect(screen.getByText('trigger.memory_elevated.title')).toBeTruthy();
    });
    fireEvent.click(screen.getByText('dismiss'));
    await waitFor(() => {
      expect(screen.queryByText('trigger.memory_elevated.title')).toBeNull();
    });
    unmount();

    // Session dismissal persists, but a worse trigger re-opens.
    mockPressure({ memory: { level: 'critical' }, disk: { state: 'ok' } });
    render(<ResourcePressureBanner />);
    await waitFor(() => {
      expect(screen.getByText('trigger.memory_critical.title')).toBeTruthy();
    });
  });
});
