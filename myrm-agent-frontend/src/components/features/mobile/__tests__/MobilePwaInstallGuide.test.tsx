/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MobilePwaInstallGuide } from '../MobilePwaInstallGuide';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('MobilePwaInstallGuide', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

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
    Object.defineProperty(window.navigator, 'userAgent', {
      writable: true,
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
    });

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
    Object.defineProperty(window.navigator, 'userAgent', {
      writable: true,
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
    });

    render(<MobilePwaInstallGuide />);

    const remindBtn = screen.getByText('remindLater');
    fireEvent.click(remindBtn);

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    const stored = localStorage.getItem('myrm_pwa_install_dismissed_until');
    expect(stored).toBeTruthy();
    expect(Number(stored)).toBeGreaterThan(Date.now());
  });
});
