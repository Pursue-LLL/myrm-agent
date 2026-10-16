import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import { getMemoryStats } from '@/services/memory/core';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('memory stats service api', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ total_memories: 3, by_type: {} });
  });

  it('keeps the global error toast on by default for the memory pages', async () => {
    await getMemoryStats();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/stats', { silent: undefined });
  });

  it('lets decorative callers suppress the global error toast', async () => {
    await getMemoryStats({ silent: true });

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/stats', { silent: true });
  });
});
