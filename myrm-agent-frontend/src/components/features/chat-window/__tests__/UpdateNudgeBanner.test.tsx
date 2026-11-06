/** @vitest-environment jsdom */
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import UpdateNudgeBanner from '../UpdateNudgeBanner';
import { useNoticeSlot } from '@/hooks/ui/useNoticeSlot';
import * as updatePrefs from '@/lib/update-prefs';

const mockPush = vi.fn();

/** Stands in for another first-screen notice that is already readable. */
function OtherNotice({ shown }: { shown: boolean }) {
  useNoticeSlot('migration-discovery', shown);
  return null;
}

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
    localStorage.clear();
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

  it('defers a regular update when the viewer dismisses it, and hides it for the session', async () => {
    const deferSpy = vi.spyOn(updatePrefs, 'setDeferredVersion');
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
    expect(deferSpy).toHaveBeenCalledWith('v0.2.0');
  });

  it('stays quiet in the next session for a dismissed version, and speaks up again for a newer one', async () => {
    vi.mocked(updatePrefs.getDeferredVersion).mockRestore();
    localStorage.clear();
    const releaseCheck = (version: string) =>
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ stale: true, latest: { version } }),
      } as Response);

    global.fetch = releaseCheck('v0.2.0');
    const first = render(<UpdateNudgeBanner />);
    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText('dismiss'));
    first.unmount();

    // A new session: the session flag is gone, only the stored deferral remains.
    sessionStorage.clear();
    global.fetch = releaseCheck('v0.2.0');
    const second = render(<UpdateNudgeBanner />);
    await act(async () => {});
    expect(global.fetch).toHaveBeenCalled();
    expect(second.container.firstChild).toBeNull();
    second.unmount();

    global.fetch = releaseCheck('v0.3.0');
    render(<UpdateNudgeBanner />);
    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });
    localStorage.clear();
  });

  it('keeps a dismissed security patch quiet for the session only, because patches bypass deferral', async () => {
    const deferSpy = vi.spyOn(updatePrefs, 'setDeferredVersion');
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
        changelog: { is_security: true },
      }),
    } as Response);

    const first = render(<UpdateNudgeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('icon-shield')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText('dismiss'));

    expect(screen.queryByTestId('icon-shield')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('update_nudge_dismissed')).toBe('true');
    expect(deferSpy).not.toHaveBeenCalled();

    // Same session: not even asked. A new session shows the patch again.
    first.unmount();
    vi.mocked(global.fetch).mockClear();
    render(<UpdateNudgeBanner />);
    expect(global.fetch).not.toHaveBeenCalled();
    sessionStorage.clear();
    render(<UpdateNudgeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('icon-shield')).toBeInTheDocument();
    });
  });

  it('stacks the copy above the actions on phones so the text keeps a readable column', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
      }),
    } as Response);

    const { container } = render(<UpdateNudgeBanner />);

    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });

    expect(container.firstElementChild).toHaveClass('w-full', 'flex-col', 'sm:flex-row');
    expect(screen.getByText('open').closest('div')).toHaveClass('shrink-0');
  });

  it('waits while another notice is on screen instead of stacking above it, then appears once that one closes', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        stale: true,
        latest: { version: 'v0.2.0' },
      }),
    } as Response);

    const { rerender } = render(
      <>
        <OtherNotice shown />
        <UpdateNudgeBanner />
      </>,
    );
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
    await act(async () => {});
    expect(screen.queryByText('open')).not.toBeInTheDocument();

    rerender(
      <>
        <OtherNotice shown={false} />
        <UpdateNudgeBanner />
      </>,
    );
    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });
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
