import { describe, expect, it } from 'vitest';

import { skillVersionOriginLabel } from '@/lib/skills/versionOrigin';

const t = (key: string) => `label:${key}`;

describe('skillVersionOriginLabel', () => {
  it.each([
    ['agent_meta_tool', 'createdByAgent'],
    ['settings_editor', 'createdByManual'],
    ['evolution_engine', 'createdBySkillGrowth'],
    ['mutation_rollback', 'createdByRollback'],
    ['batch_rollback', 'createdByRollback'],
    ['batch_import', 'createdByImport'],
    ['llm', 'createdByLlm'],
  ])('names the origin %s with the localized %s label', (createdBy, key) => {
    expect(skillVersionOriginLabel(createdBy, t)).toBe(`label:${key}`);
  });

  it.each(['', 'unknown_writer', 'constructor', '__proto__'])('never exposes the raw identifier %j', (createdBy) => {
    expect(skillVersionOriginLabel(createdBy, t)).toBeNull();
  });
});
