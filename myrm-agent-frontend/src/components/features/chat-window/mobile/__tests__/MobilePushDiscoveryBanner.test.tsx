import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MobilePushDiscoveryBanner } from '../MobilePushDiscoveryBanner';

const mockSubscribe = vi.fn();
let mockState: string = 'prompt';
let mockLoading = false;

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      pushEnableBanner: 'Enable push notifications to stay updated on task outcomes & approvals',
      pushEnableButton: 'Enable',
      pushDismiss: 'Dismiss',
    };
    return map[key] ?? key;
  },
}));

vi.mock('@/hooks/pwa/usePushSubscription', () => ({
  usePushSubscription: () => ({
    state: mockState,
    loading: mockLoading,
    subscribe: mockSubscribe,
    unsubscribe: vi.fn(),
    sendTest: vi.fn(),
    error: null,
  }),
}));

describe('MobilePushDiscoveryBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState = 'prompt';
    mockLoading = false;
    sessionStorage.clear();
  });

  it('renders discovery banner when push subscription state is prompt', () => {
    render(<MobilePushDiscoveryBanner />);
    expect(
      screen.getByText('Enable push notifications to stay updated on task outcomes & approvals'),
    ).toBeDefined();
    expect(screen.getByText('Enable')).toBeDefined();
  });

  it('renders discovery banner when state is unsubscribed', () => {
    mockState = 'unsubscribed';
    render(<MobilePushDiscoveryBanner />);
    expect(screen.getByText('Enable')).toBeDefined();
  });

  it('does not render when state is already subscribed', () => {
    mockState = 'subscribed';
    const { container } = render(<MobilePushDiscoveryBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('does not render when state is unsupported or denied', () => {
    mockState = 'denied';
    const { container } = render(<MobilePushDiscoveryBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('triggers subscribe on enable button click', () => {
    render(<MobilePushDiscoveryBanner />);
    fireEvent.click(screen.getByText('Enable'));
    expect(mockSubscribe).toHaveBeenCalledTimes(1);
  });

  it('hides banner and persists in sessionStorage when dismissed', () => {
    render(<MobilePushDiscoveryBanner />);
    const dismissBtn = screen.getByLabelText('Dismiss');
    fireEvent.click(dismissBtn);

    expect(
      screen.queryByText('Enable push notifications to stay updated on task outcomes & approvals'),
    ).toBeNull();
    expect(sessionStorage.getItem('dismissed_mobile_push_banner')).toBe('1');
  });
});
