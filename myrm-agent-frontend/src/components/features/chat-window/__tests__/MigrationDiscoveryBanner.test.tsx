/**
 * @vitest-environment jsdom
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

import type { DiscoveryResponse, ExternalSource } from '@/services/migrationDiscovery';

const DAY_MS = 24 * 60 * 60 * 1000;
const stableT = (key: string) => key;
const mockPush = vi.fn();
const mockDiscover = vi.fn<() => Promise<DiscoveryResponse>>();
const mockIsLocalMode = vi.fn(() => true);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => mockIsLocalMode(),
}));

vi.mock('@/services/migrationDiscovery', () => ({
  discoverMigrationSources: () => mockDiscover(),
  canDeepLinkMigrationSource: () => true,
  getMigrationSourceDisplayName: (id: string) => id,
}));

import MigrationDiscoveryBanner from '../MigrationDiscoveryBanner';
import { useNoticeSlot } from '@/hooks/ui/useNoticeSlot';

/** Stands in for another first-screen notice that is already readable. */
function OtherNotice({ shown }: { shown: boolean }) {
  useNoticeSlot('update-nudge', shown);
  return null;
}

const source: ExternalSource = {
  competitor: 'hermes',
  root: '/home/user/.hermes',
  confidence: 'high',
  files: [],
  memory_count_estimate: 3,
  skill_count: 2,
  has_api_keys: false,
};

const response = (sources: ExternalSource[]): DiscoveryResponse => ({
  sources,
  scan_path: '/home/user',
  available: true,
});

describe('MigrationDiscoveryBanner', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockDiscover.mockReset();
    mockIsLocalMode.mockReturnValue(true);
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders nothing while the scan is pending, so no placeholder flashes in', async () => {
    let resolveScan: (value: DiscoveryResponse) => void = () => {};
    mockDiscover.mockReturnValue(new Promise((resolve) => (resolveScan = resolve)));

    const { container } = render(<MigrationDiscoveryBanner />);
    expect(container.firstChild).toBeNull();

    await act(async () => {
      resolveScan(response([]));
    });
    expect(container.firstChild).toBeNull();
  });

  it('shows the import prompt and deep-links to the single detected source', async () => {
    mockDiscover.mockResolvedValue(response([source]));

    render(<MigrationDiscoveryBanner />);

    const importButton = await screen.findByRole('button', { name: /importButton/ });
    fireEvent.click(importButton);

    expect(mockPush).toHaveBeenCalledWith('/settings/memory?sub=migration&source=hermes');
  });

  it('lets the actions wrap onto a second line instead of running past the screen edge', async () => {
    mockDiscover.mockResolvedValue(response([source]));

    render(<MigrationDiscoveryBanner />);

    const importButton = await screen.findByRole('button', { name: /importButton/ });
    expect(importButton.parentElement).toHaveClass('flex-wrap');
  });

  it('snoozes the offer for a week after dismissal and skips the disk scan while it is snoozed', async () => {
    mockDiscover.mockResolvedValue(response([source]));
    const closedAt = Date.now();
    const { container, unmount } = render(<MigrationDiscoveryBanner />);

    fireEvent.click(await screen.findByRole('button', { name: 'dismiss' }));
    expect(container.firstChild).toBeNull();
    const snoozedUntil = Number(localStorage.getItem('myrm.proactive.dismissed.migration-discovery'));
    expect(snoozedUntil).toBeGreaterThanOrEqual(closedAt + 7 * DAY_MS);
    expect(snoozedUntil).toBeLessThanOrEqual(Date.now() + 7 * DAY_MS);

    // Even a new browser session (no session flag) stays quiet and does not scan the disk again.
    unmount();
    const remounted = render(<MigrationDiscoveryBanner />);
    await act(async () => {});
    expect(remounted.container.firstChild).toBeNull();
    expect(mockDiscover).toHaveBeenCalledTimes(1);
  });

  it('offers the import again once the week has passed', async () => {
    mockDiscover.mockResolvedValue(response([source]));
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', String(Date.now() - 1_000));

    render(<MigrationDiscoveryBanner />);

    expect(await screen.findByRole('button', { name: /importButton/ })).toBeInTheDocument();
    expect(mockDiscover).toHaveBeenCalledTimes(1);
  });

  it('waits while another notice is on screen instead of stacking above it, then appears once that one closes', async () => {
    mockDiscover.mockResolvedValue(response([source]));

    const { rerender } = render(
      <>
        <OtherNotice shown />
        <MigrationDiscoveryBanner />
      </>,
    );
    await act(async () => {});
    expect(screen.queryByRole('button', { name: /importButton/ })).toBeNull();

    rerender(
      <>
        <OtherNotice shown={false} />
        <MigrationDiscoveryBanner />
      </>,
    );
    expect(await screen.findByRole('button', { name: /importButton/ })).toBeInTheDocument();
  });

  it('does not scan outside local mode', () => {
    mockIsLocalMode.mockReturnValue(false);

    const { container } = render(<MigrationDiscoveryBanner />);

    expect(container.firstChild).toBeNull();
    expect(mockDiscover).not.toHaveBeenCalled();
  });

  it('renders nothing when the scan fails', async () => {
    mockDiscover.mockRejectedValue(new Error('scan failed'));

    const { container } = render(<MigrationDiscoveryBanner />);
    await act(async () => {});

    expect(container.firstChild).toBeNull();
  });
});
