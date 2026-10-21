import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { applyContextBundleMigration, getContextBundleHealth } from '../contextBundle';

describe('contextBundle API paths', () => {
  it('uses api/v1-relative paths without duplicate /api prefix', async () => {
    vi.mocked(apiRequest).mockResolvedValue({} as never);

    await getContextBundleHealth();
    await applyContextBundleMigration();

    expect(apiRequest).toHaveBeenNthCalledWith(1, '/context-bundle');
    expect(apiRequest).toHaveBeenNthCalledWith(2, '/context-bundle/migrate/apply', { method: 'POST' });
  });
});
