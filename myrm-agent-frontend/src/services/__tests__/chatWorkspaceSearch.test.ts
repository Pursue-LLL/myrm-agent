import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { searchWorkspaceFiles } from '@/services/chat';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('searchWorkspaceFiles', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('asks the server to search the whole workspace and leaves reporting a failure to its caller', async () => {
    const response = { results: [{ name: 'a.ts', path: '/w/src/a.ts', relative_path: 'src/a.ts', size: 3 }], total: 1 };
    apiRequestMock.mockResolvedValue(response);

    const result = await searchWorkspaceFiles('/w', 'a ts');

    expect(result).toEqual(response);
    // The Files tab explains a failed search in its own panel; a request-level toast would report it twice.
    expect(apiRequestMock).toHaveBeenCalledWith('/files/browse/search?q=a+ts&workspace=%2Fw&limit=50', {
      silent: true,
    });
  });

  it('passes a custom result limit', async () => {
    apiRequestMock.mockResolvedValue({ results: [], total: 0 });

    await searchWorkspaceFiles('/w', 'a', 10);

    expect(apiRequestMock.mock.calls[0][0]).toContain('limit=10');
  });
});
