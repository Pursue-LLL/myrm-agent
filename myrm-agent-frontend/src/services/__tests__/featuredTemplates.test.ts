import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockGetTemplates = vi.hoisted(() => vi.fn());

vi.mock('@/services/agent', () => ({
  getTemplates: (...args: unknown[]) => mockGetTemplates(...args),
}));

import { invalidateFeaturedTemplates, loadFeaturedTemplates, peekFeaturedTemplates } from '../featuredTemplates';

const template = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  name: id,
  agent_type: 'individual',
  ...extra,
});

describe('featured templates cache', () => {
  beforeEach(() => {
    mockGetTemplates.mockReset();
    invalidateFeaturedTemplates();
  });

  it('keeps teams and Pareto presets only, at most four', async () => {
    mockGetTemplates.mockResolvedValue([
      template('plain-1'),
      template('team-1', { agent_type: 'team' }),
      template('pareto-1', { is_pareto_preset: true }),
      template('team-2', { agent_type: 'team' }),
      template('team-3', { agent_type: 'team' }),
      template('team-4', { agent_type: 'team' }),
    ]);

    const featured = await loadFeaturedTemplates();

    expect(featured.map((item) => item.id)).toEqual(['team-1', 'pareto-1', 'team-2', 'team-3']);
  });

  it('shares one request between concurrent callers and serves later ones from the cache', async () => {
    mockGetTemplates.mockResolvedValue([template('team-1', { agent_type: 'team' })]);

    await Promise.all([loadFeaturedTemplates(), loadFeaturedTemplates()]);
    await loadFeaturedTemplates();

    expect(mockGetTemplates).toHaveBeenCalledTimes(1);
    expect(peekFeaturedTemplates()).toHaveLength(1);
  });

  it('expires the cache after 60 seconds', async () => {
    mockGetTemplates.mockResolvedValue([template('team-1', { agent_type: 'team' })]);
    await loadFeaturedTemplates();

    expect(peekFeaturedTemplates(Date.now() + 59_000)).not.toBeNull();
    expect(peekFeaturedTemplates(Date.now() + 61_000)).toBeNull();
  });

  it('does not cache a failure, so the next caller asks again', async () => {
    mockGetTemplates.mockRejectedValueOnce(new Error('offline'));
    await expect(loadFeaturedTemplates()).rejects.toThrow('offline');
    expect(peekFeaturedTemplates()).toBeNull();

    mockGetTemplates.mockResolvedValueOnce([template('team-1', { agent_type: 'team' })]);
    await expect(loadFeaturedTemplates()).resolves.toHaveLength(1);
    expect(mockGetTemplates).toHaveBeenCalledTimes(2);
  });

  it('ignores an answer that arrives after the cache was invalidated', async () => {
    let resolveStale: (templates: unknown[]) => void = () => {};
    mockGetTemplates.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveStale = resolve;
      }),
    );
    const stale = loadFeaturedTemplates();

    invalidateFeaturedTemplates();
    resolveStale([template('team-old', { agent_type: 'team' })]);
    await stale;

    expect(peekFeaturedTemplates()).toBeNull();
  });
});
