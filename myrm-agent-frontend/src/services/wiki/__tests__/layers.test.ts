import { describe, it, expect, vi, beforeEach } from 'vitest';
import { layersService } from '../layers';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  getApiUrl: vi.fn((path: string) => path),
}));

describe('layersService API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches layers stats', async () => {
    const mockStats = {
      agent_id: 'agent_dev',
      raw_files_count: 10,
      sources_count: 5,
      concepts_count: 12,
      claims_count: 4,
      methods_count: 3,
      templates_count: 2,
      deliverables_count: 8,
      inbox_count: 1,
    };

    vi.mocked(api.apiRequest).mockResolvedValueOnce(mockStats);

    const result = await layersService.getLayersStats('agent_dev');
    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/layers/stats?agent_id=agent_dev');
    expect(result.raw_files_count).toBe(10);
    expect(result.deliverables_count).toBe(8);
  });

  it('fetches the items of a layer with the layer key and limit', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce([]);

    await layersService.getLayerItems('deliverables', 'agent_dev', 10);
    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/layers/items?layer=deliverables&limit=10&agent_id=agent_dev');
  });
});
