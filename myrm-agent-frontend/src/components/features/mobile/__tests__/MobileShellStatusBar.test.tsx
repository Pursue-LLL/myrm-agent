/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobileShellStatusBar } from '../MobileShellStatusBar';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, unknown>) => {
    if (params && 'hostName' in params) {
      return `${key}:${String(params.hostName)}`;
    }
    return key;
  },
}));

describe('MobileShellStatusBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, 'onLine', {
      writable: true,
      configurable: true,
      value: true,
    });
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
});
