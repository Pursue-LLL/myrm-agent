import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TrustBadgeCard from '../TrustBadgeCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-ok" />,
  IconAlertCircle: () => <span data-testid="icon-fail" />,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

const mockIsTauri = vi.hoisted(() => ({ value: true }));
const mockSafety = vi.hoisted(() => ({ value: 'safe' }));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri.value,
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(async () => mockSafety.value),
}));

describe('TrustBadgeCard', () => {
  beforeEach(() => {
    mockIsTauri.value = true;
    mockSafety.value = 'safe';
  });

  it('renders signed state with official links', async () => {
    render(<TrustBadgeCard />);
    await waitFor(() => {
      expect(screen.getByText('state.safe')).toBeTruthy();
    });
    expect(screen.getByText('officialSite')).toBeTruthy();
    expect(screen.getByText('officialDownload')).toBeTruthy();
    expect(screen.getByText('officialReleases')).toBeTruthy();
  });

  it('renders honest fallback when the check cannot run', async () => {
    mockSafety.value = 'unknown';
    render(<TrustBadgeCard />);
    await waitFor(() => {
      expect(screen.getByText('state.unknown')).toBeTruthy();
    });
  });

  it('renders nothing outside Tauri', () => {
    mockIsTauri.value = false;
    const { container } = render(<TrustBadgeCard />);
    expect(container.firstChild).toBeNull();
  });
});
