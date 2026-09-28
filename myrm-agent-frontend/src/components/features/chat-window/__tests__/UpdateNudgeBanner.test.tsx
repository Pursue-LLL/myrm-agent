/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UpdateNudgeBanner from '../UpdateNudgeBanner';
import * as updatePrefs from '@/lib/update-prefs';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return Object.entries(params).reduce((acc, [k, v]) => acc.replace(`{${k}}`, String(v)), key);
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconArrowRight: () => <span data-testid="icon-arrow-right" />,
  IconDownload: () => <span data-testid="icon-download" />,
  IconShield: () => <span data-testid="icon-shield" />,
}));

const mockSessionStorage: Record<string, string> = {};
const sessionStorageMock = {
  getItem: (key: string) => mockSessionStorage[key] ?? null,
  setItem: (key: string, val: string) => {
    mockSessionStorage[key] = String(val);
  },
  removeItem: (key: string) => {
    delete mockSessionStorage[key];
  },
  clear: () => {
    for (const key of Object.keys(mockSessionStorage)) {
      delete mockSessionStorage[key];
    }
  },
  length: 0,
  key: () => null,
};

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'sessionStorage', {
    value: sessionStorageMock,
    writable: true,
  });
}

describe('UpdateNudgeBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.spyOn(updatePrefs, 'getDeferredVersion').mockReturnValue(null);
    vi.spyOn(updatePrefs, 'isQuietNow').mockReturnValue(false);
  });

  it('renders standard update banner when stale=true and no security patch', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
        changelog: { is_security: false },
      }),
    } as Response);

    render(<UpdateNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByTestId('icon-download')).toBeInTheDocument();
      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.getByText('description')).toBeInTheDocument();
    });
  });

  it('renders security update banner with IconShield when is_security=true even during quiet hours', async () => {
    vi.spyOn(updatePrefs, 'getDeferredVersion').mockReturnValue('v0.2.0');
    vi.spyOn(updatePrefs, 'isQuietNow').mockReturnValue(true);

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
        changelog: { is_security: true },
      }),
    } as Response);

    render(<UpdateNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByTestId('icon-shield')).toBeInTheDocument();
      expect(screen.getByText('securityTitle')).toBeInTheDocument();
      expect(screen.getByText('securityDescription')).toBeInTheDocument();
    });
  });

  it('hides banner when dismissed by user and sets sessionStorage', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
      }),
    } as Response);

    render(<UpdateNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });

    const dismissBtn = screen.getByLabelText('dismiss');
    fireEvent.click(dismissBtn);

    expect(screen.queryByText('open')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('update_nudge_dismissed')).toBe('true');
  });

  it('navigates to settings on click open button', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
      }),
    } as Response);

    render(<UpdateNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('open'));
    expect(mockPush).toHaveBeenCalledWith('/settings/system?sub=about');
  });
});
