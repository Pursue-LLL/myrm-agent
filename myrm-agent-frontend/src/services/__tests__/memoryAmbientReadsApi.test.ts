import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from '@/lib/api';
import { getPendingMemories, getWorkingState } from '@/services/memory/core';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('memory ambient reads', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({});
  });

  it('keeps the global error toast on for the pending queue by default', async () => {
    await getPendingMemories();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/pending', { silent: undefined });
  });

  it('lets callers that render their own error state silence the pending queue toast', async () => {
    await getPendingMemories({ silent: true });

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/pending', { silent: true });
  });

  it('still scopes the pending queue to a user when asked', async () => {
    await getPendingMemories({ userId: 'u 1' });

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/pending?user_id=u+1', { silent: undefined });
  });

  it('keeps the global error toast on for working state by default', async () => {
    await getWorkingState();

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/working-state', { silent: undefined });
  });

  it('lets decorative callers silence the working state toast', async () => {
    await getWorkingState({ silent: true });

    expect(apiRequestMock).toHaveBeenCalledWith('/memory/working-state', { silent: true });
  });
});
