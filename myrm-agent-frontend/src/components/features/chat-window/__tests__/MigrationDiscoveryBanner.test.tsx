/**
 * @vitest-environment jsdom
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

import type { DiscoveryResponse, ExternalSource } from '@/services/migrationDiscovery';

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
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
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

  it('stays hidden after dismissal for the rest of the browser session', async () => {
    mockDiscover.mockResolvedValue(response([source]));
    const { container, unmount } = render(<MigrationDiscoveryBanner />);

    fireEvent.click(await screen.findByRole('button', { name: 'dismiss' }));
    expect(container.firstChild).toBeNull();
    expect(sessionStorage.getItem('migration_discovery_dismissed')).toBe('true');

    unmount();
    const remounted = render(<MigrationDiscoveryBanner />);
    expect(remounted.container.firstChild).toBeNull();
    expect(mockDiscover).toHaveBeenCalledTimes(1);
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
