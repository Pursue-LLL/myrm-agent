import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import useConfigStore from '@/store/useConfigStore';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import { getDefaultThemeProfile } from '@/theme-engine';
import { DEFAULT_PERSONAL_SETTINGS } from '@/services/config/types';

let mockPathname = '/';

vi.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

vi.mock('../WorkspaceArtLayer', () => ({
  default: () => <div data-testid="workspace-art-layer" />,
}));

vi.mock('../ThemeAssetMissingBanner', () => ({
  default: () => <div data-testid="theme-asset-missing-banner" />,
}));

vi.mock('@/services/theme-assets/ThemeAssetStore', () => ({
  resolveThemeAssetUrl: vi.fn().mockResolvedValue(null),
  verifyThemeAssetAvailable: vi.fn().mockResolvedValue(true),
}));

vi.mock('@/lib/fonts', () => ({
  ensureFontLoaded: vi.fn(),
}));

import ThemeProfileProvider from '../ThemeProfileProvider';
import {
  resolveThemeAssetUrl,
  verifyThemeAssetAvailable,
} from '@/services/theme-assets/ThemeAssetStore';

function mockMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('ThemeProfileProvider pet-overlay art layer', () => {
  beforeEach(() => {
    mockPathname = '/';
    mockMatchMedia();
    vi.mocked(verifyThemeAssetAvailable).mockClear();
    vi.mocked(resolveThemeAssetUrl).mockClear();
    useThemeStudioDomPreviewStore.getState().clearPreview();
    useConfigStore.setState({
      personalSettings: {
        ...DEFAULT_PERSONAL_SETTINGS,
        activeThemeProfileId: getDefaultThemeProfile().id,
        themeProfiles: [],
      },
    });
  });

  it('renders WorkspaceArtLayer on normal routes', async () => {
    mockPathname = '/chat';
    render(
      <ThemeProfileProvider>
        <span data-testid="child">child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-art-layer')).toBeInTheDocument();
    });
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('skips WorkspaceArtLayer and asset banner on /pet-overlay', async () => {
    mockPathname = '/pet-overlay';
    render(
      <ThemeProfileProvider>
        <span data-testid="child">child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('workspace-art-layer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('theme-asset-missing-banner')).not.toBeInTheDocument();
  });

  it('skips WorkspaceArtLayer on nested /pet-overlay paths', async () => {
    mockPathname = '/pet-overlay/extra';
    render(
      <ThemeProfileProvider>
        <span data-testid="child">child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('workspace-art-layer')).not.toBeInTheDocument();
  });

  it('does not load theme assets on /pet-overlay', async () => {
    mockPathname = '/pet-overlay';
    render(
      <ThemeProfileProvider>
        <span data-testid="child">child</span>
      </ThemeProfileProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });
    expect(verifyThemeAssetAvailable).not.toHaveBeenCalled();
    expect(resolveThemeAssetUrl).not.toHaveBeenCalled();
  });
});
