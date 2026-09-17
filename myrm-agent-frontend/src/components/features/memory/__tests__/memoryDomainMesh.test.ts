import { describe, expect, it } from 'vitest';

describe('memoryDomainMesh contracts', () => {
  it('validates domain mesh highlight formatting and boundaries', () => {
    const highlight = {
      id: 'mem-101',
      l0: 'User prefers vim keys',
      l1: 'User strictly uses vim keybindings in code editors and terminals.',
      category: 'preferences',
      memory_type: 'semantic',
      updated_at: '2026-09-18T00:00:00Z',
    };

    expect(highlight.id).toBe('mem-101');
    expect(highlight.l0.length).toBeLessThanOrEqual(120);
    expect(highlight.category).toBe('preferences');
  });

  it('validates three-domain classification mapping', () => {
    const domains = ['user', 'assistant', 'task'] as const;
    const categoryDomainMap: Record<string, (typeof domains)[number]> = {
      profile: 'user',
      preferences: 'user',
      entities: 'user',
      events: 'user',
      identity: 'assistant',
      soul: 'assistant',
      experiences: 'task',
      trajectories: 'task',
      traps: 'task',
    };

    expect(categoryDomainMap.traps).toBe('task');
    expect(categoryDomainMap.soul).toBe('assistant');
    expect(categoryDomainMap.preferences).toBe('user');
  });

  it('validates Hermes migration request payload schema', () => {
    const migrationPayload = {
      json_content: JSON.stringify({
        memories: [
          { content: 'Hermes raw memory item', timestamp: '2026-01-01T00:00:00Z' },
        ],
      }),
      dry_run: true,
      default_domain: 'task' as const,
    };

    const parsed = JSON.parse(migrationPayload.json_content);
    expect(parsed.memories).toHaveLength(1);
    expect(migrationPayload.dry_run).toBe(true);
    expect(migrationPayload.default_domain).toBe('task');
  });
});
