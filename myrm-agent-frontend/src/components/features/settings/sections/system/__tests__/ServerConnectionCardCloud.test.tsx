import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ServerConnectionCard from '../ServerConnectionCard';

const mocks = vi.hoisted(() => ({
  switchRemoteFollow: vi.fn<(deferred: boolean) => Promise<void>>(),
  openExternal: vi.fn<(url: string) => Promise<boolean>>(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('@/lib/utils/classnameUtils', () => ({ cn: (...args: string[]) => args.filter(Boolean).join(' ') }));
vi.mock('@/lib/utils/toast', () => ({
  toast: { info: vi.fn(), success: mocks.toastSuccess, error: mocks.toastError },
}));
vi.mock('@/lib/remote-follow-switch', () => ({ switchRemoteFollow: mocks.switchRemoteFollow }));
vi.mock('@/lib/desktopBridge', () => ({ desktopBridge: { openExternal: mocks.openExternal } }));
vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return { ...actual, isTauriRuntime: () => true };
});

const CP = 'https://cp.example.com';
const ROSTER_KEY = 'myrm-remote-gateway-roster';

function readRoster(): { profiles: { kind: string; url: string }[]; activeId: string | null } {
  return JSON.parse(localStorage.getItem(ROSTER_KEY) ?? '{"profiles":[],"activeId":null}');
}

/** 当前连接的会话查询与控制平面各自应答；`'hang'` 表示会话查询永不返回（网络黑洞）；其余请求一律失败。 */
function stubBackends(options: { runningSessions: number | 'hang' }) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('active-sessions')) {
        if (options.runningSessions === 'hang') {
          return new Promise<Response>(() => undefined);
        }
        const activeSessions = Array.from({ length: options.runningSessions }, (_, index) => ({ id: `s-${index}` }));
        return Response.json({ data: { activeSessions, recentSessions: [], maxConcurrent: 0, availableSlots: 0 } });
      }
      if (url === `${CP}/api/sandboxes`) {
        return Response.json({ sandboxes: [{ id: 'sbx-1' }] });
      }
      if (url === `${CP}/api/auth/config`) {
        return Response.json({ oauth_providers: ['google'] });
      }
      throw new Error(`unexpected request: ${url}`);
    }),
  );
}

/** 渲染为远程模式并填好控制平面地址。 */
function renderCloudCard() {
  render(<ServerConnectionCard />);
  fireEvent.click(screen.getByLabelText('modeLocal'));
  fireEvent.change(screen.getByPlaceholderText('https://app.myrmagent.com'), { target: { value: CP } });
}

describe('ServerConnectionCard cloud connection', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('myrm-remote-first-run-seen', '1');
    localStorage.setItem('auth_token', 'cp-token-abc');
    mocks.switchRemoteFollow.mockReset().mockResolvedValue(undefined);
    mocks.openExternal.mockReset().mockResolvedValue(true);
    mocks.toastError.mockReset();
    mocks.toastSuccess.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  describe('discovering a sandbox', () => {
    it('switches the connection before the cloud profile is created and activated', async () => {
      stubBackends({ runningSessions: 0 });
      const atSwitch: { profiles: number; flag: boolean }[] = [];
      mocks.switchRemoteFollow.mockImplementation(async (deferred) => {
        atSwitch.push({ profiles: readRoster().profiles.length, flag: deferred });
      });
      renderCloudCard();

      fireEvent.click(screen.getByText('discoverSandbox'));

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('connected'));
      expect(atSwitch).toEqual([{ profiles: 0, flag: true }]);
      const roster = readRoster();
      expect(roster.profiles).toHaveLength(1);
      expect(roster.profiles[0]).toMatchObject({ kind: 'cloud', url: `${CP}/proxy/me` });
      expect(localStorage.getItem('myrm-connection-pending-switch')).toBeNull();
    });

    it('leaves the roster untouched and stays retryable when the switch fails', async () => {
      stubBackends({ runningSessions: 0 });
      mocks.switchRemoteFollow.mockRejectedValueOnce(new Error('sidecar refused to stop'));
      renderCloudCard();

      fireEvent.click(screen.getByText('discoverSandbox'));

      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledWith('switchFailed'));
      expect(mocks.toastSuccess).not.toHaveBeenCalled();
      expect(readRoster()).toEqual({ profiles: [], activeId: null });
      await waitFor(() => expect((screen.getByText('discoverSandbox') as HTMLButtonElement).disabled).toBe(false));

      fireEvent.click(screen.getByText('discoverSandbox'));
      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('connected'));
      expect(readRoster().profiles).toHaveLength(1);
    });

    it('asks before interrupting running sessions and switches only after the user confirms', async () => {
      stubBackends({ runningSessions: 2 });
      renderCloudCard();

      fireEvent.click(screen.getByText('discoverSandbox'));
      fireEvent.click(await screen.findByText('cancel'));

      expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
      expect(readRoster()).toEqual({ profiles: [], activeId: null });

      fireEvent.click(screen.getByText('discoverSandbox'));
      fireEvent.click(await screen.findByText('confirm'));

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('connected'));
      expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(true);
      expect(readRoster().profiles).toHaveLength(1);
    });
  });

  describe('when the current connection does not answer the session query', () => {
    afterEach(() => vi.useRealTimers());

    it('stops waiting after the timeout and proceeds with the switch', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      stubBackends({ runningSessions: 'hang' });
      renderCloudCard();

      fireEvent.click(screen.getByText('discoverSandbox'));
      await vi.advanceTimersByTimeAsync(2900);
      expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(200);
      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('connected'));
      expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(true);
    });
  });

  describe('triggering again while the session query is still pending', () => {
    afterEach(() => vi.useRealTimers());

    it('runs a single guarded switch instead of one per trigger', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      localStorage.setItem(
        ROSTER_KEY,
        JSON.stringify({
          profiles: [{ id: 'p1', name: 'Pi', url: 'http://pi.example.com', kind: 'server' }],
          activeId: 'p1',
        }),
      );
      stubBackends({ runningSessions: 'hang' });
      render(<ServerConnectionCard />);

      fireEvent.click(screen.getByLabelText('modeRemote'));
      await vi.advanceTimersByTimeAsync(500);
      fireEvent.click(screen.getByLabelText('modeRemote'));
      await vi.advanceTimersByTimeAsync(3500);

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('disconnected'));
      expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(false);
      expect(mocks.toastSuccess).toHaveBeenCalledTimes(1);
    });
  });

  describe('disconnecting back to local', () => {
    function renderConnectedCard() {
      localStorage.setItem(
        ROSTER_KEY,
        JSON.stringify({
          profiles: [{ id: 'p1', name: 'Pi', url: 'http://pi.example.com', kind: 'server' }],
          activeId: 'p1',
        }),
      );
      render(<ServerConnectionCard />);
    }

    it('asks before interrupting running sessions and switches back only after the user confirms', async () => {
      stubBackends({ runningSessions: 1 });
      renderConnectedCard();

      fireEvent.click(screen.getByLabelText('modeRemote'));
      fireEvent.click(await screen.findByText('cancel'));

      expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
      expect(readRoster().activeId).toBe('p1');

      fireEvent.click(screen.getByLabelText('modeRemote'));
      fireEvent.click(await screen.findByText('confirm'));

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('disconnected'));
      expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(false);
      expect(readRoster().activeId).toBeNull();
    });

    it('switches back immediately when nothing is running', async () => {
      stubBackends({ runningSessions: 0 });
      renderConnectedCard();

      fireEvent.click(screen.getByLabelText('modeRemote'));

      await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledWith('disconnected'));
      expect(mocks.switchRemoteFollow).toHaveBeenCalledExactlyOnceWith(false);
    });
  });

  describe('signing in through the browser', () => {
    async function clickProvider() {
      fireEvent.click(screen.getByText('checkProviders'));
      fireEvent.click(await screen.findByText('continueWith'));
    }

    it('opens the browser straight away when nothing is running', async () => {
      stubBackends({ runningSessions: 0 });
      renderCloudCard();

      await clickProvider();

      await waitFor(() => expect(mocks.openExternal).toHaveBeenCalledTimes(1));
      expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
    });

    it('asks before leaving for the browser when sessions are running, and opens it only on confirm', async () => {
      stubBackends({ runningSessions: 1 });
      renderCloudCard();

      await clickProvider();
      fireEvent.click(await screen.findByText('cancel'));

      expect(mocks.openExternal).not.toHaveBeenCalled();
      expect(localStorage.getItem('myrm-cloud-oauth-pending')).toBeNull();

      await clickProvider();
      fireEvent.click(await screen.findByText('confirm'));

      await waitFor(() => expect(mocks.openExternal).toHaveBeenCalledTimes(1));
      expect(localStorage.getItem('myrm-cloud-oauth-pending')).not.toBeNull();
      expect(mocks.switchRemoteFollow).not.toHaveBeenCalled();
    });
  });
});
