import { describe, expect, it } from 'vitest';

import {
  basenamePath,
  isSaveSkillApproval,
  normalizeSaveSkillPreviewArgs,
} from '../saveSkillApproval';

describe('isSaveSkillApproval', () => {
  it('detects OW save_skill tools', () => {
    expect(isSaveSkillApproval('save_skill', {})).toBe(true);
    expect(isSaveSkillApproval('save_skill_tool', {})).toBe(true);
  });

  it('detects harness skill_manage_tool save action', () => {
    expect(isSaveSkillApproval('skill_manage_tool', { action: 'save', name: 'demo' })).toBe(true);
    expect(isSaveSkillApproval('skill_manage_tool', { action: 'patch', name: 'demo' })).toBe(false);
  });
});

describe('normalizeSaveSkillPreviewArgs', () => {
  it('maps OW save_skill args', () => {
    expect(
      normalizeSaveSkillPreviewArgs({
        description: 'Summarize incidents',
        instructions: '# Steps\n1. Collect logs',
        files: ['scripts/run.py', 'references/guide.md'],
      }),
    ).toEqual({
      description: 'Summarize incidents',
      instructions: '# Steps\n1. Collect logs',
      files: ['scripts/run.py', 'references/guide.md'],
    });
  });

  it('maps harness skill_manage save content field', () => {
    expect(
      normalizeSaveSkillPreviewArgs({
        action: 'save',
        name: 'incident-summary',
        description: 'Incident digest',
        content: '---\nname: incident-summary\n---\n# Incident',
      }),
    ).toEqual({
      description: 'Incident digest',
      instructions: '---\nname: incident-summary\n---\n# Incident',
      files: undefined,
    });
  });
});

describe('basenamePath', () => {
  it('returns trailing segment', () => {
    expect(basenamePath('scripts/run.py')).toBe('run.py');
    expect(basenamePath('C:\\bundle\\guide.md')).toBe('guide.md');
  });
});
