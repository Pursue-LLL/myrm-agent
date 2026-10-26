import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { openVisualDesktop } from '@/lib/visualDesktopEvents';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useUserControlStore from '@/store/useUserControlStore';
import { VisualDesktopToggle } from '../VisualDesktopToggle';

const mocks = vi.hoisted(() => ({
  fetchUserSandbox: vi.fn(),
  fetchSandboxVncUrl: vi.fn(),
  fetchWithTimeout: vi.fn(),
  toastError: vi.fn(),
  // Stable identity like next-intl's: a new `t` per render would re-trigger the component's load effect.
  t: (key: string) => key,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => mocks.t,
}));

vi.mock('next/dynamic', () => ({
  default: () => (props: { wsUrl: string; viewOnly?: boolean }) => (
    <div data-testid="visual-desktop" data-ws-url={props.wsUrl} data-view-only={String(Boolean(props.viewOnly))} />
  ),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => mocks.fetchWithTimeout(...args),
}));

vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => mocks.toastError(...args) },
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
    mocks.fetchWithTimeout.mockResolvedValue({
      ok: true,
      json: async () => ({ state: 'user_takeover', learned: false }),
    });
    useBrowserTakeoverStore.getState().completeTakeover();
  });

  afterEach(async () => {
    mocks.fetchWithTimeout.mockResolvedValue({ ok: true, json: async () => ({ learned: false }) });
    await useUserControlStore.getState().release();
    useBrowserTakeoverStore.getState().completeTakeover();
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

  describe('taking and handing back control', () => {
    beforeEach(() => {
      mocks.fetchSandboxVncUrl.mockResolvedValue({
        vnc_url: 'wss://vnc.example/sb-1',
        token: 'tok',
        sandbox_id: 'sb-1',
      });
    });

    const resumeCalls = () => mocks.fetchWithTimeout.mock.calls.filter(([url]) => url === '/webui/vnc/resume');

    it('opens view-only and only lets the person drive after they take control', async () => {
      openPanel();
      const desktop = await screen.findByTestId('visual-desktop');
      expect(desktop).toHaveAttribute('data-view-only', 'true');
      expect(screen.getByText('viewOnly')).toBeInTheDocument();

      fireEvent.click(screen.getByTestId('visual-desktop-take-control'));

      await waitFor(() => expect(screen.getByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'false'));
      expect(screen.getByText('inControl')).toBeInTheDocument();
      expect(useUserControlStore.getState().held).toBe(true);
    });

    it('takes control straight away when opened with the takeover intent', async () => {
      render(<VisualDesktopToggle />);

      act(() => openVisualDesktop({ takeover: true }));

      await waitFor(() => expect(useUserControlStore.getState().held).toBe(true));
      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'false');
    });

    it('stays view-only when opened without the takeover intent', async () => {
      render(<VisualDesktopToggle />);

      act(() => openVisualDesktop());

      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'true');
      expect(mocks.fetchWithTimeout).not.toHaveBeenCalled();
    });

    it('hands control back from the control bar', async () => {
      openPanel();
      await screen.findByTestId('visual-desktop');
      fireEvent.click(screen.getByTestId('visual-desktop-take-control'));
      fireEvent.click(await screen.findByTestId('visual-desktop-hand-back'));

      await waitFor(() => expect(useUserControlStore.getState().held).toBe(false));
      expect(screen.getByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'true');
      expect(resumeCalls()).toHaveLength(1);
    });

    it('hands control back when the panel is closed, so the agent is not left waiting', async () => {
      openPanel();
      await screen.findByTestId('visual-desktop');
      fireEvent.click(screen.getByTestId('visual-desktop-take-control'));
      await screen.findByTestId('visual-desktop-hand-back');

      fireEvent.click(screen.getByRole('button', { name: 'close' }));

      await waitFor(() => expect(screen.queryByTestId('visual-desktop')).not.toBeInTheDocument());
      expect(useUserControlStore.getState().held).toBe(false);
      expect(resumeCalls()).toHaveLength(1);
    });

    it('keeps the panel open and tells the person when the hand back fails', async () => {
      openPanel();
      await screen.findByTestId('visual-desktop');
      fireEvent.click(screen.getByTestId('visual-desktop-take-control'));
      await screen.findByTestId('visual-desktop-hand-back');
      mocks.fetchWithTimeout.mockResolvedValue({ ok: false, status: 503 });

      fireEvent.click(screen.getByRole('button', { name: 'close' }));

      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('handBackFailed'));
      expect(screen.getByTestId('visual-desktop')).toBeInTheDocument();
      expect(useUserControlStore.getState().held).toBe(true);
    });

    it('tells the person when control could not be taken', async () => {
      openPanel();
      await screen.findByTestId('visual-desktop');
      mocks.fetchWithTimeout.mockResolvedValue({ ok: false, status: 501 });

      fireEvent.click(screen.getByTestId('visual-desktop-take-control'));

      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('takeControlFailed'));
      expect(screen.getByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'true');
    });

    it('leaves the hand back to Done/Skip while the agent waits on a managed takeover', async () => {
      useBrowserTakeoverStore.getState().requestTakeover({ reason: 'Solve the CAPTCHA', ui_mode: 'managed' });
      render(<VisualDesktopToggle />);
      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute('data-view-only', 'false');
      expect(screen.queryByTestId('visual-desktop-control-bar')).not.toBeInTheDocument();
      await useUserControlStore.getState().acquire('Solve the CAPTCHA');
      mocks.fetchWithTimeout.mockClear();

      fireEvent.click(screen.getByRole('button', { name: 'close' }));

      await waitFor(() => expect(screen.queryByTestId('visual-desktop')).not.toBeInTheDocument());
      expect(useUserControlStore.getState().held).toBe(true);
      expect(resumeCalls()).toHaveLength(0);
    });
  });
});
