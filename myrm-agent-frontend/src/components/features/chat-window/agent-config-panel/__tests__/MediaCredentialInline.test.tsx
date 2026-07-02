'use client';

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { BuiltinToolId } from '@/store/chat/types';

const mockProviders: { providers: object[] } = { providers: [] };

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (s: object) => unknown) =>
    selector({ imageGeneration: { model: 'dall-e-3' }, videoGeneration: { provider: 'openai' } }),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: object) => unknown) => selector(mockProviders),
}));

vi.mock('@/lib/utils/mediaProviderStatus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils/mediaProviderStatus')>();
  return {
    ...actual,
    fetchMediaProviderStatus: vi.fn(async () => ({})),
  };
});

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(async () => null),
}));

import { fetchMediaProviderStatus } from '@/lib/utils/mediaProviderStatus';
import { MediaCredentialInline } from '../MediaCredentialInline';

describe('MediaCredentialInline', () => {
  const tPanel = (key: string) => key;

  beforeEach(() => {
    vi.mocked(fetchMediaProviderStatus).mockClear();
    mockProviders.providers = [];
  });

  it('renders nothing when no media tools enabled', async () => {
    const enabled: BuiltinToolId[] = ['web_search', 'memory'];
    const { container } = render(
      <MediaCredentialInline enabledBuiltinTools={enabled} tPanel={tPanel} />,
    );
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
    expect(fetchMediaProviderStatus).not.toHaveBeenCalled();
  });

  it('shows amber warning when image_generation enabled without credentials', async () => {
    const enabled: BuiltinToolId[] = ['image_generation'];
    render(<MediaCredentialInline enabledBuiltinTools={enabled} tPanel={tPanel} />);

    await waitFor(() => {
      expect(screen.getByText('mediaCredential.title')).toBeInTheDocument();
    });
    expect(screen.getByText('mediaCredential.imageMissing')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'mediaCredential.openSettings' })).toHaveAttribute(
      'href',
      '/settings/models?sub=default',
    );
    expect(fetchMediaProviderStatus).toHaveBeenCalled();
  });

  it('hides warning when openai provider has active api key', async () => {
    mockProviders.providers = [
      {
        id: 'openai',
        isEnabled: true,
        routingProfile: 'openai',
        apiKeys: [{ key: 'sk-test', isActive: true }],
      },
    ];

    const enabled: BuiltinToolId[] = ['image_generation'];
    const { container } = render(
      <MediaCredentialInline enabledBuiltinTools={enabled} tPanel={tPanel} />,
    );

    await waitFor(() => {
      expect(fetchMediaProviderStatus).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });
});
