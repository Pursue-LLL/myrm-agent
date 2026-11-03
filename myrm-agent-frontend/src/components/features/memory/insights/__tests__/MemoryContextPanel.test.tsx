/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const memoryServiceMock = vi.hoisted(() => ({ getMemoryContext: vi.fn() }));
vi.mock('@/services/memory', () => memoryServiceMock);

import MemoryContextPanel from '../MemoryContextPanel';

beforeEach(() => {
  memoryServiceMock.getMemoryContext.mockReset();
});

describe('MemoryContextPanel localized copy', () => {
  it('renders both profile cards with translated headings and their entries', async () => {
    memoryServiceMock.getMemoryContext.mockResolvedValue({
      global_profile: { language: 'Chinese' },
      peer_profile: { tone: 'Direct' },
    });
    render(<MemoryContextPanel />);

    expect(await screen.findByText('contextGlobalTitle')).toBeInTheDocument();
    expect(screen.getByText('contextGlobalSubtitle')).toBeInTheDocument();
    expect(screen.getByText('contextPeerTitle')).toBeInTheDocument();
    expect(screen.getByText('contextPeerSubtitle')).toBeInTheDocument();
    expect(screen.getByText('Chinese')).toBeInTheDocument();
    expect(screen.getByText('Direct')).toBeInTheDocument();
    expect(screen.queryByText('contextGlobalEmpty')).not.toBeInTheDocument();
  });

  it('shows a translated empty message in each card when the profiles are empty', async () => {
    memoryServiceMock.getMemoryContext.mockResolvedValue({ global_profile: {}, peer_profile: {} });
    render(<MemoryContextPanel />);

    expect(await screen.findByText('contextGlobalEmpty')).toBeInTheDocument();
    expect(screen.getByText('contextPeerEmpty')).toBeInTheDocument();
  });
});
