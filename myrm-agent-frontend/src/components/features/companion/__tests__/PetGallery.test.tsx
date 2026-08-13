import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const setSpriteConfigMock = vi.fn();
const setSpriteEnabledMock = vi.fn();
const saveConfigToServerMock = vi.fn();

const companionStoreState: Record<string, unknown> = {
  spriteConfig: { petSlug: 'nous-girl', displayName: 'Nous Girl', contentSha256: 'abc123' },
  setSpriteConfig: setSpriteConfigMock,
  setSpriteEnabled: setSpriteEnabledMock,
  saveConfigToServer: saveConfigToServerMock,
};

vi.mock('@/store/useCompanionStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector(companionStoreState),
}));

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (key === 'gallery.count') {return `${values?.count ?? 0} pets`;}
  const labels: Record<string, string> = {
    'gallery.loading': 'Loading pets...',
    'gallery.error': 'Failed to load pet gallery',
    'gallery.installedTitle': 'Installed',
    'gallery.manifestOffline': 'Catalog unavailable right now.',
    'gallery.searchPlaceholder': 'Search pets...',
    'gallery.installError': 'Failed to install pet',
    'gallery.uninstall': 'Remove',
    'gallery.uninstallConfirm': 'Remove this pet?',
    'gallery.uninstallError': 'Failed to remove pet',
    'gallery.cancel': 'Cancel',
  };
  return labels[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/services/companion/petSpritesheet', () => ({
  companionPetSpritesheetUrl: (slug: string) => `/api/v1/companion/pets/${slug}/spritesheet`,
}));

const listInstalledCompanionPetsMock = vi.fn();
const installCompanionPetMock = vi.fn();
const uninstallCompanionPetMock = vi.fn();

vi.mock('@/services/companion/petInstall', () => ({
  listInstalledCompanionPets: () => listInstalledCompanionPetsMock(),
  installCompanionPet: (...args: unknown[]) => installCompanionPetMock(...args),
  uninstallCompanionPet: (...args: unknown[]) => uninstallCompanionPetMock(...args),
}));

import PetGallery from '@/components/features/companion/PetGallery';

class MockIntersectionObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}

describe('PetGallery local-first', () => {
  beforeAll(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
  });

  afterAll(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    companionStoreState.spriteConfig = {
      petSlug: 'nous-girl',
      displayName: 'Nous Girl',
      contentSha256: 'abc123',
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Manifest fetch failed: 503')),
    );
    listInstalledCompanionPetsMock.mockResolvedValue([
      { slug: 'nous-girl', display_name: 'Nous Girl', content_sha256: 'abc123' },
      { slug: 'lobster', display_name: 'Lobster', content_sha256: 'def456' },
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('shows installed pets when manifest fails (fail-open)', async () => {
    render(<PetGallery />);

    await waitFor(() => {
      expect(screen.getByTestId('pet-gallery-installed')).toBeTruthy();
      expect(screen.getByTestId('pet-gallery-offline-hint')).toBeTruthy();
    });
    expect(screen.queryByText('Failed to load pet gallery')).toBeNull();
  });

  it('activates installed pet without calling install API', async () => {
    render(<PetGallery />);

    await waitFor(() => {
      expect(screen.getByTestId('installed-pet-lobster')).toBeTruthy();
    });

    fireEvent.click(screen.getByTestId('installed-pet-lobster'));

    await waitFor(() => {
      expect(setSpriteConfigMock).toHaveBeenCalledWith({
        petSlug: 'lobster',
        displayName: 'Lobster',
        contentSha256: 'def456',
      });
    });
    expect(setSpriteEnabledMock).toHaveBeenCalledWith(true);
    expect(saveConfigToServerMock).toHaveBeenCalled();
    expect(installCompanionPetMock).not.toHaveBeenCalled();
  });

  it('shows hard error when manifest fails and nothing installed', async () => {
    companionStoreState.spriteConfig = null;
    listInstalledCompanionPetsMock.mockResolvedValueOnce([]);
    render(<PetGallery />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load pet gallery')).toBeTruthy();
    });
    expect(screen.queryByTestId('pet-gallery-installed')).toBeNull();
  });

  it('syncs installed row when spriteConfig changes from external slash install', async () => {
    listInstalledCompanionPetsMock.mockResolvedValue([
      { slug: 'nous-girl', display_name: 'Nous Girl', content_sha256: 'abc123' },
    ]);

    const { rerender } = render(<PetGallery reloadInstalledWhen />);

    await waitFor(() => {
      expect(screen.getByTestId('installed-pet-nous-girl')).toBeTruthy();
    });
    expect(screen.queryByTestId('installed-pet-lobster')).toBeNull();

    companionStoreState.spriteConfig = {
      petSlug: 'lobster',
      displayName: 'Lobster',
      contentSha256: 'def456',
    };
    rerender(<PetGallery reloadInstalledWhen />);

    await waitFor(() => {
      expect(screen.getByTestId('installed-pet-lobster')).toBeTruthy();
    });
  });

  it('uninstalls active pet and clears sprite config', async () => {
    uninstallCompanionPetMock.mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(<PetGallery />);

    await waitFor(() => {
      expect(screen.getByTestId('installed-pet-menu-nous-girl')).toBeTruthy();
    });

    await user.click(screen.getByTestId('installed-pet-menu-nous-girl'));
    await user.click(screen.getByTestId('installed-pet-uninstall-nous-girl'));

    await waitFor(() => {
      expect(screen.getByText('Remove this pet?')).toBeTruthy();
    });

    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' });
    await user.click(confirmButtons[confirmButtons.length - 1]!);

    await waitFor(() => {
      expect(uninstallCompanionPetMock).toHaveBeenCalledWith('nous-girl');
      expect(setSpriteConfigMock).toHaveBeenCalledWith(null);
      expect(setSpriteEnabledMock).toHaveBeenCalledWith(false);
      expect(saveConfigToServerMock).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.queryByTestId('installed-pet-nous-girl')).toBeNull();
    });
  });

  it('shows uninstall error message when DELETE fails', async () => {
    uninstallCompanionPetMock.mockRejectedValueOnce(new Error('Pet not installed'));

    render(<PetGallery />);

    await waitFor(() => {
      expect(screen.getByTestId('installed-pet-menu-nous-girl')).toBeTruthy();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId('installed-pet-menu-nous-girl'));
    await user.click(screen.getByTestId('installed-pet-uninstall-nous-girl'));

    const confirmButtons = screen.getAllByRole('button', { name: 'Remove' });
    await user.click(confirmButtons[confirmButtons.length - 1]!);

    await waitFor(() => {
      expect(screen.getByTestId('pet-gallery-uninstall-error')).toHaveTextContent('Pet not installed');
    });
  });
});
