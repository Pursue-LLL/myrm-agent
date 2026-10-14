/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import ProviderOAuthSection from '../ProviderOAuthSection';

const stableT = (key: string, values?: Record<string, string>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const { toastSuccess, toastError } = vi.hoisted(() => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));

vi.mock('sonner', () => ({
  toast: { success: toastSuccess, error: toastError },
}));

const { apiRequest } = vi.hoisted(() => ({ apiRequest: vi.fn() }));

vi.mock('@/lib/api', () => ({ apiRequest }));

const { mockWriteToClipboard } = vi.hoisted(() => ({ mockWriteToClipboard: vi.fn() }));

vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard: mockWriteToClipboard }));

const { mockConnect, mockDisconnect } = vi.hoisted(() => ({ mockConnect: vi.fn(), mockDisconnect: vi.fn() }));

vi.mock('@/store/config/providerSubscription', () => ({
  connectProviderSubscription: mockConnect,
  disconnectProviderSubscription: mockDisconnect,
}));

const START = '/integrations/xai/oauth/start';
const POLL = '/integrations/xai/oauth/poll?user_code=ABCD-1234';
const DISCONNECT = '/integrations/provider-oauth/disconnect/xai';

const AUTHORIZATION = {
  user_code: 'ABCD-1234',
  verification_uri: 'https://x.ai/device',
  verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
  expires_in: 600,
  interval: 5,
};

type Routes = Record<string, () => unknown>;

function serve(routes: Routes) {
  apiRequest.mockImplementation(async (path: string) => {
    const handler = routes[path];
    if (!handler) {
      throw new Error(`Unexpected request: ${path}`);
    }
    return handler();
  });
}

function requestsTo(path: string) {
  return apiRequest.mock.calls.filter(([requested]) => requested === path);
}

type SectionProps = React.ComponentProps<typeof ProviderOAuthSection>;

async function renderSection(props: Partial<SectionProps> = {}) {
  const view = render(<ProviderOAuthSection providerId="xai" connected={false} hasApiKey={false} {...props} />);
  await act(async () => {});
  return view;
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function startLogin() {
  fireEvent.click(screen.getByText('loginButton'));
  await act(async () => {});
}

describe('ProviderOAuthSection', () => {
  let openSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    mockConnect.mockResolvedValue(undefined);
  });

  afterEach(() => {
    openSpy.mockRestore();
    vi.useRealTimers();
  });

  it.each(['anthropic', 'openai', 'copilot', 'custom-unknown'])('renders nothing for the %s provider', async (id) => {
    serve({});
    const { container } = await renderSection({ providerId: id });

    expect(container.firstChild).toBeNull();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('offers the SuperGrok login with its notice while not connected, without asking the server anything', async () => {
    serve({});
    await renderSection();

    expect(screen.getByText('noticeTitle')).toBeInTheDocument();
    expect(screen.getByText('noticeBody')).toBeInTheDocument();
    expect(screen.getByText('loginPrompt')).toBeInTheDocument();
    expect(screen.getByText('loginButton')).toBeInTheDocument();
    expect(screen.queryByText('connected')).not.toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it.each([
    [false, 'connectedWithQuota'],
    [true, 'connectedWithApiKey'],
  ])('shows the persisted connection (api key: %s)', async (hasApiKey, message) => {
    serve({});
    await renderSection({ connected: true, hasApiKey });

    expect(screen.getByText('connected')).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByText('disconnect')).toBeInTheDocument();
    expect(screen.queryByText('loginButton')).not.toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('opens the pre-filled verification page, shows the code and applies the connection once approved', async () => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'success' }) });
    await renderSection();

    await startLogin();

    expect(requestsTo(START)[0][1]).toEqual({ method: 'POST' });
    expect(openSpy).toHaveBeenCalledWith('https://x.ai/device?code=ABCD-1234', '_blank', 'noopener,noreferrer');
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
    expect(screen.getByText('waiting')).toBeInTheDocument();
    expect(requestsTo(POLL)).toHaveLength(0);

    await advance(5000);

    expect(requestsTo(POLL)[0][1]).toEqual({ method: 'POST', silent: true });
    expect(mockConnect).toHaveBeenCalledExactlyOnceWith('xai');
    expect(toastSuccess).toHaveBeenCalledWith('toast.connected');
    expect(screen.queryByText('ABCD-1234')).not.toBeInTheDocument();
  });

  it('shows the connection as soon as the provider is marked connected', async () => {
    serve({});
    const { rerender } = await renderSection();

    rerender(<ProviderOAuthSection providerId="xai" connected hasApiKey={false} />);

    expect(screen.getByText('connectedWithQuota')).toBeInTheDocument();
  });

  it('copies the device code through the shared clipboard helper', async () => {
    mockWriteToClipboard.mockResolvedValue(true);
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    fireEvent.click(screen.getByLabelText('copyCode'));
    await act(async () => {});

    expect(mockWriteToClipboard).toHaveBeenCalledExactlyOnceWith('ABCD-1234', true);
  });

  it('keeps showing the code when the clipboard refuses the copy', async () => {
    mockWriteToClipboard.mockResolvedValue(false);
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    fireEvent.click(screen.getByLabelText('copyCode'));
    await act(async () => {});

    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
  });

  it('slows down by five seconds when the provider asks to', async () => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending', slow_down: true }) });
    await renderSection();
    await startLogin();

    await advance(5000);
    expect(requestsTo(POLL)).toHaveLength(1);
    await advance(9999);
    expect(requestsTo(POLL)).toHaveLength(1);
    await advance(1);
    expect(requestsTo(POLL)).toHaveLength(2);
  });

  it('keeps polling through a transient network error', async () => {
    let attempts = 0;
    serve({
      [START]: () => AUTHORIZATION,
      [POLL]: () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error('network down');
        }
        return { status: 'pending' };
      },
    });
    await renderSection();
    await startLogin();

    await advance(5000);
    await advance(5000);

    expect(requestsTo(POLL)).toHaveLength(2);
    expect(toastError).not.toHaveBeenCalled();
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
  });

  it.each([
    ['expired', 'toast.expired'],
    ['denied', 'toast.denied'],
  ])('returns to the login prompt with a message when the authorization is %s', async (status, message) => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status }) });
    await renderSection();
    await startLogin();

    await advance(5000);
    await advance(30000);

    expect(toastError).toHaveBeenCalledWith(message);
    expect(requestsTo(POLL)).toHaveLength(1);
    expect(mockConnect).not.toHaveBeenCalled();
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('gives up when the device code lifetime ends without an answer', async () => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    await advance(605_000);

    expect(toastError).toHaveBeenCalledWith('toast.timeout');
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('stops polling when the login is cancelled', async () => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    await renderSection();
    await startLogin();

    fireEvent.click(screen.getByText('cancel'));
    await advance(30000);

    expect(requestsTo(POLL)).toHaveLength(0);
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('stops polling when the section unmounts', async () => {
    serve({ [START]: () => AUTHORIZATION, [POLL]: () => ({ status: 'pending' }) });
    const { unmount } = await renderSection();
    await startLogin();

    unmount();
    await advance(30000);

    expect(requestsTo(POLL)).toHaveLength(0);
  });

  it('reports a failed start without opening anything', async () => {
    serve({
      [START]: () => {
        throw new Error('boom');
      },
    });
    await renderSection();

    await startLogin();

    expect(toastError).toHaveBeenCalledWith('toast.startFailed');
    expect(openSpy).not.toHaveBeenCalled();
    expect(screen.getByText('loginButton')).toBeInTheDocument();
  });

  it('treats a start response without a code or page as a failed start', async () => {
    serve({ [START]: () => ({ interval: 5 }) });
    await renderSection();

    await startLogin();

    expect(toastError).toHaveBeenCalledWith('toast.startFailed');
    expect(openSpy).not.toHaveBeenCalled();
    await advance(30000);
    expect(requestsTo(POLL)).toHaveLength(0);
  });

  it('disconnects on the server and then in the app', async () => {
    serve({ [DISCONNECT]: () => undefined });
    await renderSection({ connected: true });

    fireEvent.click(screen.getByText('disconnect'));
    await act(async () => {});

    expect(requestsTo(DISCONNECT)[0][1]).toEqual({ method: 'DELETE' });
    expect(mockDisconnect).toHaveBeenCalledExactlyOnceWith('xai');
    expect(toastSuccess).toHaveBeenCalledWith('toast.disconnected');
  });

  it('stays connected and says so when disconnecting fails', async () => {
    serve({
      [DISCONNECT]: () => {
        throw new Error('boom');
      },
    });
    await renderSection({ connected: true });

    fireEvent.click(screen.getByText('disconnect'));
    await act(async () => {});

    expect(toastError).toHaveBeenCalledWith('toast.disconnectFailed');
    expect(mockDisconnect).not.toHaveBeenCalled();
    expect(screen.getByText('connected')).toBeInTheDocument();
  });
});
