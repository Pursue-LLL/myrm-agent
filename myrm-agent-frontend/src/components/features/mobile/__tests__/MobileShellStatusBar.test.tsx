/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobileShellStatusBar } from '../MobileShellStatusBar';

// `undefined` models Node >= 21, which exposes a `navigator` object without `onLine`.
function setOnLine(value: boolean | undefined) {
  Object.defineProperty(navigator, 'onLine', { writable: true, configurable: true, value });
}

const stableT = (key: string, params?: Record<string, unknown>) => {
    if (params && 'hostName' in params) {
      return `${key}:${String(params.hostName)}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MobileShellStatusBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setOnLine(true);
  });

  it('renders online ready status by default with host name', () => {
    render(<MobileShellStatusBar hostName="NAS-Home" isStandalone={true} />);

    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByText('connectedTo NAS-Home')).toBeInTheDocument();
    expect(screen.getByText('PWA')).toBeInTheDocument();
  });

  it('toggles thin client connection details on pill click', () => {
    render(<MobileShellStatusBar hostName="NAS-Home" isStandalone={false} />);

    const toggleBtn = screen.getByRole('button', { name: 'networkDetailsToggle' });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('thinClientSecurity')).toBeInTheDocument();
    expect(screen.getByText('browserShell')).toBeInTheDocument();
    expect(screen.getByText('zeroLocalExecution')).toBeInTheDocument();

    // Close details
    const closeBtn = screen.getByText('close');
    fireEvent.click(closeBtn);
    expect(screen.queryByText('thinClientSecurity')).not.toBeInTheDocument();
  });

  it('renders connecting banner when isConnecting is true', () => {
    render(<MobileShellStatusBar isConnecting={true} />);

    expect(screen.getByText('connectingNotice')).toBeInTheDocument();
  });

  it('renders disconnected alert banner and triggers retry when offline or hasError', () => {
    const onRetry = vi.fn();
    render(<MobileShellStatusBar hasError={true} onRetry={onRetry} />);

    expect(screen.getByText('connectionErrorNotice')).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: 'retryButton' });
    fireEvent.click(retryBtn);

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('follows the browser going offline and back online', () => {
    render(<MobileShellStatusBar />);
    expect(screen.queryByText('offlineNotice')).not.toBeInTheDocument();

    act(() => {
      setOnLine(false);
      window.dispatchEvent(new Event('offline'));
    });
    expect(screen.getByText('offlineNotice')).toBeInTheDocument();

    act(() => {
      setOnLine(true);
      window.dispatchEvent(new Event('online'));
    });
    expect(screen.queryByText('offlineNotice')).not.toBeInTheDocument();
  });

  it('shows the offline notice when the page opens without a connection', () => {
    setOnLine(false);
    render(<MobileShellStatusBar />);

    expect(screen.getByText('offlineNotice')).toBeInTheDocument();
  });

  it('stops listening to connectivity events once unmounted', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = render(<MobileShellStatusBar />);
    unmount();

    const removed = removeSpy.mock.calls.map(([type]) => type);
    expect(removed).toEqual(expect.arrayContaining(['online', 'offline']));
    removeSpy.mockRestore();
  });

  describe('server rendering', () => {
    it('renders the connected state although Node reports no navigator.onLine', () => {
      setOnLine(undefined);

      const html = renderToString(<MobileShellStatusBar />);

      expect(html).not.toContain('offlineNotice');
      expect(html).toContain('connectedReady');
    });

    it('hydrates the server markup without a mismatch and then adopts the real connectivity', async () => {
      setOnLine(undefined);
      const serverHtml = renderToString(<MobileShellStatusBar />);
      const container = document.createElement('div');
      container.innerHTML = serverHtml;
      document.body.appendChild(container);

      const onRecoverableError = vi.fn();
      setOnLine(true);
      let root: Root | undefined;
      await act(async () => {
        root = hydrateRoot(container, <MobileShellStatusBar />, { onRecoverableError });
      });
      expect(onRecoverableError).not.toHaveBeenCalled();
      expect(container.textContent).toContain('connectedReady');

      await act(async () => {
        setOnLine(false);
        window.dispatchEvent(new Event('offline'));
      });
      expect(container.textContent).toContain('offlineNotice');

      await act(async () => {
        root?.unmount();
      });
      container.remove();
    });
  });
});
