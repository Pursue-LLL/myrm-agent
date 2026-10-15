/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SUPPORTED_INTEGRATIONS, type OauthIntegration } from '../credentialsConstants';
import { useCredentialsOAuth } from '../useCredentialsOAuth';

const { mockToast, apiRequest, mockStart, mockPoll, mockConnect, mockDisconnect } = vi.hoisted(() => ({
  mockToast: vi.fn(),
  apiRequest: vi.fn(),
  mockStart: vi.fn(),
  mockPoll: vi.fn(),
  mockConnect: vi.fn(),
  mockDisconnect: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, string>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: mockToast }));
vi.mock('@/lib/api', () => ({ apiRequest }));
vi.mock('@/services/xai-oauth', () => ({ startXaiOAuth: mockStart, pollXaiOAuth: mockPoll }));
vi.mock('@/store/config/providerSubscription', () => ({
  connectProviderSubscription: mockConnect,
  disconnectProviderSubscription: mockDisconnect,
}));
vi.mock('@/services/memory/integration', () => ({ countProviderTrees: vi.fn().mockResolvedValue(0) }));
vi.mock('@/services/google-workspace-oauth', () => ({
  disconnectGoogleWorkspaceOAuth: vi.fn(),
  fetchGoogleWorkspaceOAuthConfig: vi.fn(),
  fetchGoogleWorkspaceOAuthStatus: vi.fn().mockResolvedValue({ connected: false }),
  openGoogleAuthorizationUrl: vi.fn(),
  pollGoogleWorkspaceOAuthState: vi.fn(),
  startGoogleWorkspaceOAuth: vi.fn(),
}));

function registeredIntegration(id: string): OauthIntegration {
  const integration = SUPPORTED_INTEGRATIONS.find((candidate) => candidate.id === id);
  if (!integration) {
    throw new Error(`The ${id} integration is not registered`);
  }
  return integration;
}

const XAI = registeredIntegration('xai');
const DISCONNECT = '/integrations/provider-oauth/disconnect/xai';

const AUTHORIZATION = {
  user_code: 'ABCD-1234',
  verification_uri: 'https://x.ai/device',
  verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
  expires_in: 600,
  interval: 5,
};

describe('useCredentialsOAuth: xAI subscription', () => {
  let openSpy: ReturnType<typeof vi.spyOn>;

  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  async function connect(hook: ReturnType<typeof renderHook<ReturnType<typeof useCredentialsOAuth>, unknown>>) {
    await act(async () => {
      await hook.result.current.openConnectModal(XAI);
    });
    await act(async () => {
      await hook.result.current.handleXaiOAuthConnect();
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    apiRequest.mockResolvedValue([]);
    mockStart.mockResolvedValue(AUTHORIZATION);
    mockPoll.mockResolvedValue({ status: 'pending' });
    mockConnect.mockResolvedValue(undefined);
  });

  afterEach(() => {
    openSpy.mockRestore();
    vi.useRealTimers();
  });

  it('opens the pre-filled verification page and exposes the code while waiting', async () => {
    const hook = renderHook(() => useCredentialsOAuth());
    expect(hook.result.current).toMatchObject({ xaiOauthPolling: false, xaiUserCode: '', xaiVerificationUrl: '' });

    await connect(hook);

    expect(openSpy).toHaveBeenCalledWith('https://x.ai/device?code=ABCD-1234', '_blank', 'noopener,noreferrer');
    expect(hook.result.current).toMatchObject({
      xaiOauthPolling: true,
      xaiUserCode: 'ABCD-1234',
      xaiVerificationUrl: 'https://x.ai/device?code=ABCD-1234',
    });
  });

  it('marks the provider connected, closes the dialog and reloads the credentials once approved', async () => {
    mockPoll.mockResolvedValue({ status: 'success' });
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);
    apiRequest.mockClear();

    await advance(5000);

    expect(mockConnect).toHaveBeenCalledExactlyOnceWith('xai');
    expect(mockToast).toHaveBeenCalledWith({ title: 'connectSuccess:{"name":"xAI / SuperGrok"}' });
    expect(hook.result.current.connectModalTarget).toBeNull();
    expect(hook.result.current.xaiOauthPolling).toBe(false);
    expect(apiRequest).toHaveBeenCalledWith('/integrations/oauth', { silent: true });
  });

  it.each([
    ['expired', 'connectError:{"name":"xAI / SuperGrok"}'],
    ['denied', 'connectError:{"name":"xAI / SuperGrok"}'],
  ] as const)('tells the user the authorization %s without exposing server detail', async (status, title) => {
    mockPoll.mockResolvedValue({ status, error: 'invalid_grant: raw server detail' });
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);

    await advance(5000);

    expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title, variant: 'destructive' });
    expect(mockConnect).not.toHaveBeenCalled();
    expect(hook.result.current.xaiOauthPolling).toBe(false);
  });

  it('tells the user when the authorization times out', async () => {
    mockStart.mockResolvedValue({ ...AUTHORIZATION, expires_in: 10 });
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);

    await advance(10000);

    expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'xaiOauthTimeout', variant: 'destructive' });
  });

  it('tells the user when the authorization cannot be started, without exposing the error', async () => {
    mockStart.mockRejectedValue(new Error('503 upstream detail'));
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);

    expect(openSpy).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledExactlyOnceWith({
      title: 'connectError:{"name":"xAI / SuperGrok"}',
      variant: 'destructive',
    });
    expect(hook.result.current.xaiOauthPolling).toBe(false);
  });

  it('stops polling when the dialog is closed', async () => {
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);

    act(() => hook.result.current.closeConnectModal());
    await advance(60000);

    expect(mockPoll).not.toHaveBeenCalled();
    expect(hook.result.current).toMatchObject({ xaiOauthPolling: false, xaiUserCode: '', connectModalTarget: null });
  });

  it('stops polling when the section unmounts', async () => {
    const hook = renderHook(() => useCredentialsOAuth());
    await connect(hook);

    hook.unmount();
    await advance(60000);

    expect(mockPoll).not.toHaveBeenCalled();
  });

  describe('disconnect', () => {
    async function confirmDisconnect(
      hook: ReturnType<typeof renderHook<ReturnType<typeof useCredentialsOAuth>, unknown>>,
    ) {
      await act(async () => {
        await hook.result.current.prepareDisconnect(XAI);
      });
      await act(async () => {
        await hook.result.current.handleDisconnectOauth();
      });
    }

    it('disconnects on the server and then clears the flag in the app', async () => {
      const hook = renderHook(() => useCredentialsOAuth());

      await confirmDisconnect(hook);

      expect(apiRequest).toHaveBeenCalledWith(DISCONNECT, { method: 'DELETE' });
      expect(mockDisconnect).toHaveBeenCalledExactlyOnceWith('xai');
      expect(mockToast).toHaveBeenCalledWith({ title: 'disconnectSuccess:{"name":"xAI / SuperGrok"}' });
      expect(hook.result.current.disconnectConfirmTarget).toBeNull();
    });

    it('leaves the app state alone when the server refuses', async () => {
      apiRequest.mockImplementation(async (path: string) => {
        if (path === DISCONNECT) {
          throw new Error('404');
        }
        return [];
      });
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const hook = renderHook(() => useCredentialsOAuth());

      await confirmDisconnect(hook);

      expect(mockDisconnect).not.toHaveBeenCalled();
      expect(mockToast).toHaveBeenCalledWith({
        title: 'disconnectError:{"name":"xAI / SuperGrok"}',
        variant: 'destructive',
      });
    });
  });
});
