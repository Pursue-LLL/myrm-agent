import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MemoryRecallDegradedBanner } from '@/components/features/message-box/MemoryRecallDegradedBanner';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/memory/health', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/memory/health')>()),
  getSharedContextMemoryHealth: vi.fn(),
}));

import { EMBEDDING_NOT_CONFIGURED_REASON, getSharedContextMemoryHealth } from '@/services/memory/health';

const notConfiguredHealth = (reason: string, model: string) => ({
  ready: false,
  status: 'not_configured' as const,
  model,
  api_base_configured: false,
  api_key_configured: false,
  probed: false,
  reason,
  retryable: false,
  checked_at: new Date().toISOString(),
});

describe('MemoryRecallDegradedBanner', () => {
  it('renders when health is not ready', async () => {
    vi.mocked(getSharedContextMemoryHealth).mockResolvedValue({
      ready: false,
      status: 'unreachable',
      model: 'text-embedding-3-small',
      api_base_configured: true,
      api_key_configured: false,
      probed: false,
      retryable: true,
      checked_at: new Date().toISOString(),
    });

    render(<MemoryRecallDegradedBanner />);
    expect(await screen.findByTestId('memory-recall-degraded-banner')).toBeInTheDocument();
    expect(screen.getByText('title')).toBeInTheDocument();
  });

  it('hides when health is ready', async () => {
    vi.mocked(getSharedContextMemoryHealth).mockResolvedValue({
      ready: true,
      status: 'ready',
      model: 'text-embedding-3-small',
      api_base_configured: true,
      api_key_configured: true,
      probed: false,
      retryable: false,
      checked_at: new Date().toISOString(),
    });

    render(<MemoryRecallDegradedBanner />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByTestId('memory-recall-degraded-banner')).not.toBeInTheDocument();
  });

  it('shows unavailable state when health API fails', async () => {
    vi.mocked(getSharedContextMemoryHealth).mockRejectedValue(new Error('network'));

    render(<MemoryRecallDegradedBanner />);
    expect(await screen.findByTestId('memory-recall-degraded-banner')).toBeInTheDocument();
    expect(screen.getByText('unavailable')).toBeInTheDocument();
  });

  describe('when no embedding model was ever configured', () => {
    it('stays visible by default, as on the memory center page', async () => {
      vi.mocked(getSharedContextMemoryHealth).mockResolvedValue(
        notConfiguredHealth(EMBEDDING_NOT_CONFIGURED_REASON, ''),
      );

      render(<MemoryRecallDegradedBanner />);
      expect(await screen.findByTestId('memory-recall-degraded-banner')).toBeInTheDocument();
    });

    it('is hidden where hideWhenNotConfigured is set, because keyword recall is the default mode', async () => {
      vi.mocked(getSharedContextMemoryHealth).mockResolvedValue(
        notConfiguredHealth(EMBEDDING_NOT_CONFIGURED_REASON, ''),
      );

      render(<MemoryRecallDegradedBanner hideWhenNotConfigured />);
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(vi.mocked(getSharedContextMemoryHealth)).toHaveBeenCalled();
      expect(screen.queryByTestId('memory-recall-degraded-banner')).not.toBeInTheDocument();
    });

    it('still warns about a configured model whose API key is missing, even with hideWhenNotConfigured', async () => {
      vi.mocked(getSharedContextMemoryHealth).mockResolvedValue(
        notConfiguredHealth('missing_embedding_api_key', 'text-embedding-3-small'),
      );

      render(<MemoryRecallDegradedBanner hideWhenNotConfigured />);
      expect(await screen.findByTestId('memory-recall-degraded-banner')).toBeInTheDocument();
    });
  });
});
