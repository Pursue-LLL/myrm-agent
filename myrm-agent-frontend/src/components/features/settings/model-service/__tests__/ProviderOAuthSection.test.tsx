/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import ProviderOAuthSection from '../ProviderOAuthSection';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/services/provider-oauth', () => ({
  getProviderOAuthProviderByProviderId: (id: string) => (id === 'anthropic' ? 'anthropic' : null),
  getProviderOAuthConfig: () => ({
    flow: 'pkce',
    providerId: 'anthropic',
    name: 'Claude Pro/Max',
    nameZh: 'Claude Pro/Max 订阅',
  }),
  startProviderOAuth: vi.fn(),
  pollProviderOAuth: vi.fn(),
  fetchProviderOAuthStatus: vi.fn().mockResolvedValue({ connected: false }),
  disconnectProviderOAuth: vi.fn(),
}));

describe('ProviderOAuthSection Honest Notice Contract', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders honest policy and quota notice when provider is anthropic', () => {
    render(<ProviderOAuthSection providerId="anthropic" hasApiKey={false} />);
    expect(screen.getByText('Anthropic Subscription Policy & Quota Notice')).toBeDefined();
    expect(
      screen.getByText(/Anthropic policy may restrict third-party client subscriptions/i),
    ).toBeDefined();
  });

  it('does not render for unknown providers', () => {
    const { container } = render(<ProviderOAuthSection providerId="custom-unknown" hasApiKey={false} />);
    expect(container.firstChild).toBeNull();
  });
});
