/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import {
  makeEntry,
  makeOauthEntry,
  makeStoredConfig,
  mockApiRequest,
  mockGateMcpEnable,
  mockSetMCPConfigs,
  mockShellOpen,
  mockToast,
  resetConnectDialogMocks,
  restoreConnectDialogGlobals,
  storeState,
} from './connectDialogTestKit';

vi.mock('next-intl', async () => (await import('./connectDialogTestKit')).nextIntlMock);
vi.mock('@/hooks/shared/useToast', async () => (await import('./connectDialogTestKit')).toastMock);
vi.mock('@/store/useConfigStore', async () => (await import('./connectDialogTestKit')).configStoreMock);
vi.mock('@/lib/api', async () => (await import('./connectDialogTestKit')).apiMock);
vi.mock('@/hooks/settings/useMcpSecurityGate', async () => (await import('./connectDialogTestKit')).securityGateMock);
vi.mock('@/lib/utils/mcp-config', async () => (await import('./connectDialogTestKit')).mcpConfigUtilsMock);
vi.mock(
  '@/components/features/settings/mcp/MCPScanAckDialog',
  async () => (await import('./connectDialogTestKit')).scanAckDialogMock,
);
vi.mock('@/lib/deploy-mode', async () => (await import('./connectDialogTestKit')).deployModeMock);
vi.mock('@tauri-apps/plugin-shell', async () => (await import('./connectDialogTestKit')).tauriShellMock);

import { IntegrationConnectDialog } from '../../IntegrationConnectDialog';

const POLL_ID = 4242;
const OAUTH_POLL_INTERVAL_MS = 2000;
const AUTHORIZATION_URL = 'https://gh.example/authorize?state=s1';

function renderDialog(entry = makeOauthEntry()) {
  const onClose = vi.fn();
  const onConnected = vi.fn();
  const view = render(
    <IntegrationConnectDialog entry={entry} locale="en" onClose={onClose} onConnected={onConnected} />,
  );
  return { ...view, onClose, onConnected };
}

function clickConnect() {
  fireEvent.click(screen.getByRole('button', { name: 'connect' }));
}

/** Captures the OAuth status poller so a test can drive its ticks without real timers. */
function interceptOauthPolling() {
  const realSetInterval = globalThis.setInterval.bind(globalThis);
  const realClearInterval = globalThis.clearInterval.bind(globalThis);
  const poller: { tick: (() => Promise<void>) | null } = { tick: null };
  vi.spyOn(globalThis, 'setInterval').mockImplementation(((handler: () => void, delay?: number) => {
    if (delay === OAUTH_POLL_INTERVAL_MS) {
      poller.tick = handler as () => Promise<void>;
      return POLL_ID;
    }
    return realSetInterval(handler, delay);
  }) as unknown as typeof setInterval);
  const clearSpy = vi
    .spyOn(globalThis, 'clearInterval')
    .mockImplementation(((id?: number) =>
      id === POLL_ID ? undefined : realClearInterval(id)) as unknown as typeof clearInterval);
  const tick = () =>
    act(async () => {
      await poller.tick?.();
    });
  return { poller, clearSpy, tick };
}

async function startOauth() {
  const polling = interceptOauthPolling();
  mockApiRequest.mockResolvedValueOnce({ authorization_url: AUTHORIZATION_URL, state: 's1' });
  const dialog = renderDialog();
  clickConnect();
  await waitFor(() => expect(polling.poller.tick).not.toBeNull());
  return { ...polling, ...dialog };
}

describe('IntegrationConnectDialog oauth flow', () => {
  beforeEach(() => {
    resetConnectDialogMocks();
    vi.spyOn(window, 'open').mockReturnValue(null);
  });
  afterEach(restoreConnectDialogGlobals);

  it('starts the flow, opens the authorization page and waits for approval', async () => {
    await startOauth();

    expect(mockApiRequest).toHaveBeenCalledExactlyOnceWith('/integrations/mcp/oauth/start', {
      method: 'POST',
      body: JSON.stringify({
        server_name: 'gh',
        authorization_endpoint: 'https://gh.example/authorize',
        token_endpoint: 'https://gh.example/token',
        client_id: 'cid',
        client_secret: 'csec',
        scope: 'repo',
        redirect_uri: 'http://127.0.0.1:8080/api/v1/integrations/mcp/oauth/callback',
      }),
    });
    expect(window.open).toHaveBeenCalledExactlyOnceWith(AUTHORIZATION_URL, '_blank');
    expect(screen.getByRole('button', { name: 'waitingAuth' })).toBeDisabled();
  });

  it('opens the authorization page through the desktop shell inside Tauri', async () => {
    Object.defineProperty(window, '__TAURI__', { value: {}, configurable: true });

    await startOauth();

    expect(mockShellOpen).toHaveBeenCalledExactlyOnceWith(AUTHORIZATION_URL);
    expect(window.open).not.toHaveBeenCalled();
  });

  it('keeps polling through pending states and status errors', async () => {
    const { clearSpy, tick } = await startOauth();

    mockApiRequest.mockResolvedValueOnce({ status: 'pending' });
    await tick();
    mockApiRequest.mockRejectedValueOnce(new Error('flaky'));
    await tick();

    expect(mockApiRequest).toHaveBeenNthCalledWith(2, '/integrations/mcp/oauth/status/s1', { silent: true });
    expect(mockApiRequest).toHaveBeenCalledTimes(3);
    expect(clearSpy).not.toHaveBeenCalledWith(POLL_ID);
    expect(mockToast).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'waitingAuth' })).toBeDisabled();
  });

  it('sends the authorized service through the security gate and stores it', async () => {
    const { clearSpy, tick, onConnected } = await startOauth();

    mockApiRequest.mockResolvedValueOnce({ status: 'success' });
    await tick();

    expect(clearSpy).toHaveBeenCalledWith(POLL_ID);
    expect(mockGateMcpEnable).toHaveBeenCalledExactlyOnceWith(
      {
        name: 'gh',
        type: 'streamable_http',
        url: 'https://gh.example/mcp',
        command: '',
        args: [],
        description: 'GitHub',
        enabled: true,
        extra_params: null,
      },
      { acknowledgedHighRisks: false },
    );
    expect(mockSetMCPConfigs).toHaveBeenCalledTimes(1);
    expect(onConnected).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
  });

  it('does not duplicate a service that is already stored when authorization succeeds', async () => {
    storeState.mcpConfigs = [makeStoredConfig('gh')];
    const { tick, onConnected } = await startOauth();

    mockApiRequest.mockResolvedValueOnce({ status: 'success' });
    await tick();

    expect(mockSetMCPConfigs).not.toHaveBeenCalled();
    expect(mockToast).toHaveBeenCalledExactlyOnceWith({ title: 'connectSuccess' });
    expect(onConnected).toHaveBeenCalledTimes(1);
  });

  it('stops polling and reports an expired session', async () => {
    const { clearSpy, tick } = await startOauth();

    mockApiRequest.mockResolvedValueOnce({ status: 'expired_or_invalid' });
    await tick();

    expect(clearSpy).toHaveBeenCalledWith(POLL_ID);
    expect(mockToast).toHaveBeenCalledExactlyOnceWith({
      title: 'connectFailed',
      description: 'OAuth session expired',
      variant: 'destructive',
    });
    expect(mockGateMcpEnable).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
  });

  it('stops polling when the dialog unmounts', async () => {
    const { clearSpy, unmount } = await startOauth();

    unmount();

    expect(clearSpy).toHaveBeenCalledWith(POLL_ID);
  });

  it('reports a failed start and re-enables the button', async () => {
    const { poller } = interceptOauthPolling();
    mockApiRequest.mockRejectedValueOnce(new Error('boom'));
    renderDialog();

    clickConnect();

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledExactlyOnceWith({
        title: 'connectFailed',
        description: 'Error: boom',
        variant: 'destructive',
      }),
    );
    expect(poller.tick).toBeNull();
    expect(window.open).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
  });

  it('rejects entries without oauth settings', async () => {
    renderDialog(makeEntry({ authType: 'oauth2', mcpConfig: { name: 'gh', type: 'sse', url: 'https://gh.example' } }));

    clickConnect();

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledExactlyOnceWith({
        title: 'connectFailed',
        description: 'Missing OAuth config',
        variant: 'destructive',
      }),
    );
    expect(mockApiRequest).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'connect' })).toBeEnabled();
  });
});
