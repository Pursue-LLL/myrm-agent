import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VisualDesktopToggle } from '../VisualDesktopToggle';

const mocks = vi.hoisted(() => ({
  fetchUserSandbox: vi.fn(),
  fetchSandboxVncUrl: vi.fn(),
  // Stable identity like next-intl's: a new `t` per render would re-trigger the component's load effect.
  t: (key: string) => key,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => mocks.t,
}));

vi.mock('next/dynamic', () => ({
  default: () => (props: { wsUrl: string }) => <div data-testid="visual-desktop" data-ws-url={props.wsUrl} />,
}));

vi.mock('@/lib/deploy-mode', () => ({ isSandbox: () => true }));

vi.mock('@/hooks/billing/useFeatureEntitlements', () => ({
  useFeatureEntitlements: () => ({ canUseVnc: true, isLoading: false }),
}));

vi.mock('@/hooks/approval/useBrowserTakeoverActions', () => ({
  useBrowserTakeoverActions: () => ({ handleTakeoverComplete: vi.fn(), handleTakeoverSkip: vi.fn() }),
}));

vi.mock('@/lib/cp-sandbox', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/cp-sandbox')>()),
  fetchUserSandbox: mocks.fetchUserSandbox,
  fetchSandboxVncUrl: mocks.fetchSandboxVncUrl,
}));

function openPanel() {
  render(<VisualDesktopToggle />);
  fireEvent.click(screen.getByRole('button', { name: 'toggleTitle' }));
}

describe('VisualDesktopToggle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchUserSandbox.mockResolvedValue({ id: 'sb-1', user_id: 'u-1', status: 'active', vnc_url: null });
  });

  it('shows the load failure and a reconnect action when the sandbox has no VNC endpoint', async () => {
    mocks.fetchSandboxVncUrl.mockResolvedValue({ vnc_url: '', token: 'tok', sandbox_id: 'sb-1' });

    openPanel();

    expect(await screen.findByText('loadFailed')).toBeInTheDocument();
    expect(screen.queryByTestId('visual-desktop')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'reconnect' })).toHaveLength(2);
  });

  it('retries from the reconnect action and recovers once the sandbox has a VNC endpoint', async () => {
    mocks.fetchSandboxVncUrl
      .mockResolvedValueOnce({ vnc_url: '', token: 'tok', sandbox_id: 'sb-1' })
      .mockResolvedValueOnce({ vnc_url: 'wss://vnc.example/sb-1', token: 'tok', sandbox_id: 'sb-1' });

    openPanel();
    await screen.findByText('loadFailed');
    fireEvent.click(screen.getAllByRole('button', { name: 'reconnect' })[0]);

    const desktop = await screen.findByTestId('visual-desktop');
    expect(desktop).toHaveAttribute('data-ws-url', 'wss://vnc.example/sb-1?token=tok');
    expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
  });

  it('renders the desktop when the sandbox has a VNC endpoint', async () => {
    mocks.fetchSandboxVncUrl.mockResolvedValue({ vnc_url: 'wss://vnc.example/sb-1', token: 'tok', sandbox_id: 'sb-1' });

    openPanel();

    await waitFor(() => expect(screen.getByTestId('visual-desktop')).toBeInTheDocument());
    expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
  });
});
