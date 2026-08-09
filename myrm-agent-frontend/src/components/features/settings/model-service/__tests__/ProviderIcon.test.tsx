import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ProviderIcon from '../ProviderIcon';
import { resetProviderBrandIconCacheForTests } from '../provider-brand-icon-loaders';

vi.mock('../provider-brand-icon-loaders', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../provider-brand-icon-loaders')>();
  return {
    ...actual,
    getCachedProviderBrandIconUrl: vi.fn(() => undefined),
    loadProviderBrandIconUrl: vi.fn(async (providerId: string) => {
      if (providerId === 'openai') return '/mock/openai.svg';
      return null;
    }),
  };
});

describe('ProviderIcon', () => {
  beforeEach(() => {
    resetProviderBrandIconCacheForTests();
    vi.clearAllMocks();
  });

  it('renders brand svg for built-in provider after lazy load', async () => {
    render(<ProviderIcon providerId="openai" providerName="OpenAI" size={18} />);
    await waitFor(() => {
      const img = document.querySelector('img');
      expect(img).not.toBeNull();
      expect(img).toHaveAttribute('src', '/mock/openai.svg');
    });
  });

  it('falls back to letter avatar for custom provider', () => {
    render(<ProviderIcon providerId="custom-gateway" providerName="My Gateway" size={18} />);
    expect(screen.getByText('M')).toBeInTheDocument();
    expect(screen.queryByRole('img', { hidden: true })).not.toBeInTheDocument();
  });
});
