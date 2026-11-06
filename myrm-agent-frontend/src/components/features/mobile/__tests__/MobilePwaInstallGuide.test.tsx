/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobilePwaInstallGuide } from '../MobilePwaInstallGuide';

const stableT = (key: string) => key;

const DESKTOP_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36';
const IPHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15';
const ANDROID_UA = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36';

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

function setUserAgent(value: string): void {
  Object.defineProperty(window.navigator, 'userAgent', { writable: true, configurable: true, value });
}

/** Fires the browser's install offer the way Chrome does: cancelable, with `prompt()` and `userChoice`. */
function fireInstallOffer(outcome: 'accepted' | 'dismissed'): { offer: Event; prompt: ReturnType<typeof vi.fn> } {
  const prompt = vi.fn().mockResolvedValue(undefined);
  const offer = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
    prompt,
    userChoice: Promise.resolve({ outcome }),
  });
  act(() => {
    window.dispatchEvent(offer);
  });
  return { offer, prompt };
}

describe('MobilePwaInstallGuide', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    setUserAgent(DESKTOP_UA);

    // Default: not standalone
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('renders nothing if already in standalone mode', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('standalone'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const { container } = render(<MobilePwaInstallGuide />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders iOS guidance banner when userAgent matches iOS and opens steps dialog', () => {
    setUserAgent(IPHONE_UA);

    render(<MobilePwaInstallGuide />);

    expect(screen.getByRole('complementary', { name: 'installGuideTitle' })).toBeInTheDocument();
    expect(screen.getByText('viewSteps')).toBeInTheDocument();

    // Click view steps
    fireEvent.click(screen.getByText('viewSteps'));

    expect(screen.getByRole('dialog', { name: 'iosStepsTitle' })).toBeInTheDocument();
    expect(screen.getByText('iosStep1')).toBeInTheDocument();
    expect(screen.getByText('iosStep2')).toBeInTheDocument();
    expect(screen.getByText('iosStep3')).toBeInTheDocument();

    // Close dialog
    fireEvent.click(screen.getByText('gotIt'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('dismisses guide and sets expiration timestamp when clicking remind later', () => {
    setUserAgent(IPHONE_UA);

    render(<MobilePwaInstallGuide />);

    const remindBtn = screen.getByText('remindLater');
    fireEvent.click(remindBtn);

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    const stored = localStorage.getItem('myrm.proactive.dismissed.pwa-install');
    expect(stored).toBeTruthy();
    expect(Number(stored)).toBeGreaterThan(Date.now());
  });

  it('stays hidden while the snooze runs and returns once it has expired', () => {
    setUserAgent(IPHONE_UA);

    localStorage.setItem('myrm.proactive.dismissed.pwa-install', String(Date.now() + 60_000));
    const snoozed = render(<MobilePwaInstallGuide />);
    expect(snoozed.container).toBeEmptyDOMElement();
    snoozed.unmount();

    localStorage.setItem('myrm.proactive.dismissed.pwa-install', String(Date.now() - 1_000));
    render(<MobilePwaInstallGuide />);
    expect(screen.getByRole('complementary', { name: 'installGuideTitle' })).toBeInTheDocument();
  });

  it('offers the manual steps on Android until the browser hands over its install offer', () => {
    setUserAgent(ANDROID_UA);

    render(<MobilePwaInstallGuide />);
    expect(screen.getByText('installNow')).toBeInTheDocument();

    fireEvent.click(screen.getByText('installNow'));
    expect(screen.getByRole('dialog', { name: 'installStepsTitle' })).toBeInTheDocument();
    expect(screen.getByText('androidStepManual')).toBeInTheDocument();
  });

  it('shows nothing on a desktop browser until it hands over an install offer, and takes the offer over', () => {
    const { container } = render(<MobilePwaInstallGuide />);
    expect(container).toBeEmptyDOMElement();

    const { offer } = fireInstallOffer('accepted');

    expect(offer.defaultPrevented).toBe(true);
    expect(screen.getByRole('complementary', { name: 'installGuideTitle' })).toBeInTheDocument();
  });

  it('closes the guide once the install offer is accepted', async () => {
    render(<MobilePwaInstallGuide />);
    const { prompt } = fireInstallOffer('accepted');

    await act(async () => {
      fireEvent.click(screen.getByText('installNow'));
    });

    expect(prompt).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });

  it('keeps the guide when the install offer is declined', async () => {
    render(<MobilePwaInstallGuide />);
    const { prompt } = fireInstallOffer('dismissed');

    await act(async () => {
      fireEvent.click(screen.getByText('installNow'));
    });

    expect(prompt).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('complementary', { name: 'installGuideTitle' })).toBeInTheDocument();
  });

  it('leaves the browser offer alone while the guide is snoozed or the app is already installed', () => {
    localStorage.setItem('myrm.proactive.dismissed.pwa-install', String(Date.now() + 60_000));
    const snoozed = render(<MobilePwaInstallGuide />);
    expect(fireInstallOffer('accepted').offer.defaultPrevented).toBe(false);
    expect(snoozed.container).toBeEmptyDOMElement();
    snoozed.unmount();

    localStorage.clear();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({ matches: query.includes('standalone') }));
    const installed = render(<MobilePwaInstallGuide />);
    expect(fireInstallOffer('accepted').offer.defaultPrevented).toBe(false);
    expect(installed.container).toBeEmptyDOMElement();
  });

  it('hydrates the empty server markup without a mismatch and then offers the guide', async () => {
    setUserAgent(IPHONE_UA);
    const serverHtml = renderToString(<MobilePwaInstallGuide />);
    expect(serverHtml).toBe('');

    const container = document.createElement('div');
    container.innerHTML = serverHtml;
    document.body.appendChild(container);
    const onRecoverableError = vi.fn();
    let root: Root | undefined;
    await act(async () => {
      root = hydrateRoot(container, <MobilePwaInstallGuide />, { onRecoverableError });
    });

    expect(onRecoverableError).not.toHaveBeenCalled();
    expect(screen.getByRole('complementary', { name: 'installGuideTitle' })).toBeInTheDocument();

    await act(async () => {
      root?.unmount();
    });
    container.remove();
  });

  it('stays closed after the viewer closes it, even if the browser offers again', async () => {
    setUserAgent(ANDROID_UA);
    render(<MobilePwaInstallGuide />);

    fireEvent.click(screen.getByText('remindLater'));
    await waitFor(() => expect(screen.queryByRole('complementary')).not.toBeInTheDocument());

    fireInstallOffer('accepted');
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });
});
