import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import useConfigStore from '@/store/useConfigStore';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import { getDefaultThemeProfile, buildArtOverlayProfile } from '@/theme-engine';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/chat',
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

// Surface the compiled art decision instead of real DOM playback.
vi.mock('../WorkspaceArtLayer', () => ({
  default: ({ art }: { art: { enabled: boolean; mediaKind: string; mediaUrl: string | null } }) => (
    <div
      data-testid="workspace-art-layer"
      data-enabled={String(art.enabled)}
      data-kind={art.mediaKind}
      data-url={art.mediaUrl ?? ''}
    />
  ),
}));

vi.mock('../ThemeAssetMissingBanner', () => ({
  default: () => <div data-testid="theme-asset-missing-banner" />,
}));

vi.mock('@/services/theme-assets/ThemeAssetStore', () => ({
  resolveThemeAssetUrl: vi.fn(async (ref: string | null) => (ref ? `asset://resolved/${ref}` : null)),
  verifyThemeAssetAvailable: vi.fn().mockResolvedValue(true),
}));

vi.mock('@/lib/fonts', () => ({
  ensureFontLoaded: vi.fn(),
}));

import ThemeProfileProvider from '../ThemeProfileProvider';

type MediaListener = (event: { matches: boolean }) => void;

const mediaState = new Map<string, boolean>();
const mediaListeners = new Map<string, Set<MediaListener>>();

function installMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return mediaState.get(query) ?? false;
      },
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: (_event: string, listener: MediaListener) => {
        const set = mediaListeners.get(query) ?? new Set<MediaListener>();
        set.add(listener);
        mediaListeners.set(query, set);
      },
      removeEventListener: (_event: string, listener: MediaListener) => {
        mediaListeners.get(query)?.delete(listener);
      },
      dispatchEvent: vi.fn(),
    })),
  });
}

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

function flipReducedMotion(next: boolean) {
  mediaState.set(REDUCED_MOTION, next);
  for (const listener of mediaListeners.get(REDUCED_MOTION) ?? []) {
    listener({ matches: next });
  }
}

describe('ThemeProfileProvider reactive media queries', () => {
  beforeEach(() => {
    mediaState.clear();
    mediaListeners.clear();
    installMatchMedia();
    useThemeStudioDomPreviewStore.getState().clearPreview();

    const base = getDefaultThemeProfile();
    // A user-uploaded video background with a poster, the only art kind the compile context gates on.
    const overlay = buildArtOverlayProfile(base, 'asset://clip.mp4', 'video', 'asset://poster.png');
    useConfigStore.setState({
      personalSettings: {
        ...DEFAULT_PERSONAL_SETTINGS,
        activeThemeProfileId: base.id,
        themeProfiles: [overlay],
      },
    });
  });

  it('starts the user video background playing when the system allows motion', async () => {
    mediaState.set(REDUCED_MOTION, false);
    render(
      <ThemeProfileProvider>
        <span>child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-art-layer')).toHaveAttribute('data-enabled', 'true');
    });
    expect(screen.getByTestId('workspace-art-layer')).toHaveAttribute('data-kind', 'video');
  });

  it('keeps the still poster for someone who already asked for reduced motion', async () => {
    mediaState.set(REDUCED_MOTION, true);
    render(
      <ThemeProfileProvider>
        <span>child</span>
      </ThemeProfileProvider>,
    );

    // Giving up the render-time read must not trade the flip bug for a first-paint flash of video; the
    // resolved video URL only arrives after the asset effect anyway, so the poster shows first.
    await waitFor(() => {
      expect(screen.getByTestId('workspace-art-layer')).toHaveAttribute(
        'data-url',
        'asset://resolved/asset://poster.png',
      );
    });
    expect(screen.getByTestId('workspace-art-layer')).toHaveAttribute('data-kind', 'image');
  });

  it('falls back to the still poster when the system flips to reduced motion mid-session', async () => {
    mediaState.set(REDUCED_MOTION, false);
    render(
      <ThemeProfileProvider>
        <span>child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-art-layer')).toHaveAttribute('data-kind', 'video');
    });

    // The OS setting changes while the page stays open; a render-time one-shot read would miss it.
    await act(async () => {
      flipReducedMotion(true);
    });

    await waitFor(() => {
      const art = screen.getByTestId('workspace-art-layer');
      expect(art).toHaveAttribute('data-kind', 'image');
      expect(art).toHaveAttribute('data-url', 'asset://resolved/asset://poster.png');
    });
  });
});
