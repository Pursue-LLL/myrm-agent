import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiRequestMock = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  };
});

import { ApiError } from '@/lib/api';
import {
  CompanionFeatureDisabledError,
  installCompanionPet,
  listInstalledCompanionPets,
  uninstallCompanionPet,
} from '@/services/companion/petInstall';

describe('listInstalledCompanionPets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns pets from GET /companion/pets', async () => {
    apiRequestMock.mockResolvedValueOnce({
      pets: [{ slug: 'nous-girl', display_name: 'Nous Girl', content_sha256: 'abc123' }],
    });

    const pets = await listInstalledCompanionPets();
    expect(apiRequestMock).toHaveBeenCalledWith('/companion/pets', { silent: true });
    expect(pets).toEqual([{ slug: 'nous-girl', display_name: 'Nous Girl', content_sha256: 'abc123' }]);
  });

  it('returns empty array when pets field is missing', async () => {
    apiRequestMock.mockResolvedValueOnce({});
    await expect(listInstalledCompanionPets()).resolves.toEqual([]);
  });
});

describe('installCompanionPet', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('POSTs slug to install endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({
      slug: 'lobster',
      display_name: 'Lobster',
      content_sha256: 'deadbeef',
    });

    const installed = await installCompanionPet('lobster');
    expect(apiRequestMock).toHaveBeenCalledWith('/companion/pets/install', {
      method: 'POST',
      body: JSON.stringify({ slug: 'lobster' }),
      silent: true,
    });
    expect(installed.slug).toBe('lobster');
  });

  it('maps companion feature gate 403 to CompanionFeatureDisabledError', async () => {
    apiRequestMock.mockRejectedValueOnce(new ApiError('Forbidden', 403));

    await expect(installCompanionPet('lobster')).rejects.toBeInstanceOf(CompanionFeatureDisabledError);
  });

  it('rethrows non-403 ApiError unchanged', async () => {
    const err = new ApiError('Not found', 404);
    apiRequestMock.mockRejectedValueOnce(err);

    await expect(installCompanionPet('lobster')).rejects.toBe(err);
  });
});

describe('uninstallCompanionPet', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('DELETEs slug from uninstall endpoint', async () => {
    apiRequestMock.mockResolvedValueOnce({ removed: true });

    await uninstallCompanionPet('lobster');
    expect(apiRequestMock).toHaveBeenCalledWith('/companion/pets/lobster', {
      method: 'DELETE',
      silent: true,
    });
  });

  it('URL-encodes slug for DELETE', async () => {
    apiRequestMock.mockResolvedValueOnce({ removed: true });

    await uninstallCompanionPet('my pet');
    expect(apiRequestMock).toHaveBeenCalledWith('/companion/pets/my%20pet', {
      method: 'DELETE',
      silent: true,
    });
  });
});
