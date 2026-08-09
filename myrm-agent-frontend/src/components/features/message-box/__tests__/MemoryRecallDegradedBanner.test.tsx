import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MemoryRecallDegradedBanner } from '@/components/features/message-box/MemoryRecallDegradedBanner';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/memory-health', () => ({
  getSharedContextMemoryHealth: vi.fn(),
}));

import { getSharedContextMemoryHealth } from '@/services/memory-health';

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
});
