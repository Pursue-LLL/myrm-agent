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
  getProviderOAuthProviderByProviderId: (id: string) => {
    if (id === 'anthropic') return 'anthropic';
    if (id === 'xai') return 'xai';
    return null;
  },
  getProviderOAuthConfig: (provider: string) => ({
    flow: 'device_code',
    providerId: provider,
    name: provider === 'anthropic' ? 'Claude Pro/Max' : 'SuperGrok',
    nameZh: provider === 'anthropic' ? 'Claude Pro/Max 订阅' : 'SuperGrok 订阅',
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
    expect(screen.getAllByText('Anthropic Subscription Policy & Quota Notice')[0]).toBeDefined();
    expect(screen.getAllByText(/Anthropic policy may restrict third-party client subscriptions/i)[0]).toBeDefined();
  });

  it('does not render for unknown providers', () => {
    const { container } = render(<ProviderOAuthSection providerId="custom-unknown" hasApiKey={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders SuperGrok subscription notice when provider is xai', () => {
    render(<ProviderOAuthSection providerId="xai" hasApiKey={false} />);
    expect(screen.getAllByText('SuperGrok Subscription Notice')[0]).toBeDefined();
    expect(
      screen.getAllByText(/After SuperGrok authorization, you can directly use Grok models/i)[0],
    ).toBeDefined();
  });
});
