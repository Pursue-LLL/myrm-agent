import { describe, expect, it } from 'vitest';

import { completionCriteriaToText, type CompletionCriteria, type CompletionCriterion } from '@/services/kanban';

describe('completionCriteriaToText', () => {
  it('passes plain-string criteria through verbatim', () => {
    expect(completionCriteriaToText('file must exist')).toBe('file must exist');
    expect(completionCriteriaToText('')).toBe('');
  });

  it('renders semantic dicts as markdown checklist lines', () => {
    const criteria: CompletionCriterion[] = [
      { type: 'semantic', criteria: 'Covers 5 competitors' },
      { type: 'semantic', criteria: 'Links sources' },
    ];
    expect(completionCriteriaToText(criteria)).toBe('- Covers 5 competitors\n- Links sources');
  });

  it('falls back to command for shell criteria', () => {
    const criteria: CompletionCriterion[] = [{ type: 'shell', command: 'test -f /out.csv', timeout_seconds: 60 }];
    expect(completionCriteriaToText(criteria)).toBe('- test -f /out.csv');
  });

  it('skips empty entries and mixed string items', () => {
    const criteria = [
      'plain string item',
      { type: 'semantic', criteria: '' },
      { type: 'shell', command: '' },
      { type: 'semantic', criteria: 'kept item' },
    ] as CompletionCriteria;
    expect(completionCriteriaToText(criteria)).toBe('- plain string item\n- kept item');
  });

  it('returns empty for null / undefined / non-array junk', () => {
    expect(completionCriteriaToText(null)).toBe('');
    expect(completionCriteriaToText(undefined)).toBe('');
  });
});
