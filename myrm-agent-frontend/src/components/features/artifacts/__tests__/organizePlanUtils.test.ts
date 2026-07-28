import { describe, expect, it } from 'vitest';
import {
  isOrganizePlanArtifact,
  parseOrganizePlan,
  removeOrganizePlanItem,
  serializeOrganizePlan,
  updateOrganizePlanItem,
} from '../organizePlanUtils';

const samplePlan = {
  version: 1,
  scope_root: 'inbox',
  preset: 'project',
  items: [
    { src: 'inbox/a.md', dst: 'inbox/docs/a.md', reason: 'md to docs' },
    { src: 'inbox/b.png', dst: 'inbox/images/b.png', reason: 'images together' },
  ],
};

describe('organizePlanUtils', () => {
  it('detects organize plan artifact filenames', () => {
    expect(isOrganizePlanArtifact('inbox.organize-plan.json')).toBe(true);
    expect(isOrganizePlanArtifact('plan.json')).toBe(false);
  });

  it('parses valid organize plan JSON', () => {
    const parsed = parseOrganizePlan(JSON.stringify(samplePlan));
    expect(parsed?.scope_root).toBe('inbox');
    expect(parsed?.items).toHaveLength(2);
  });

  it('rejects invalid organize plan JSON', () => {
    expect(parseOrganizePlan('{bad json')).toBeNull();
    expect(parseOrganizePlan(JSON.stringify({ version: 2, scope_root: 'x', items: [] }))).toBeNull();
  });

  it('updates and removes plan items', () => {
    const parsed = parseOrganizePlan(JSON.stringify(samplePlan));
    expect(parsed).not.toBeNull();
    if (!parsed) {
      return;
    }
    const updated = updateOrganizePlanItem(parsed, 0, { dst: 'inbox/archive/a.md' });
    expect(updated.items[0]?.dst).toBe('inbox/archive/a.md');
    const trimmed = removeOrganizePlanItem(updated, 1);
    expect(trimmed.items).toHaveLength(1);
    expect(serializeOrganizePlan(trimmed)).toContain('inbox/archive/a.md');
  });
});
