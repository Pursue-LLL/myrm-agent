import { describe, expect, it } from 'vitest';

import { resolveWikiSectionLabel, wikiSectionLabeler } from '../sectionLabels';

const translate = (key: string): string => `<${key}>`;

describe('resolveWikiSectionLabel', () => {
  it('words the section the server routes the catalog through in the interface language', () => {
    expect(resolveWikiSectionLabel('index_routing', translate)).toBe('<kb_section_index_routing>');
  });

  it('leaves any other section as it is, and has no label for a missing one', () => {
    expect(resolveWikiSectionLabel('Rollback', translate)).toBe('Rollback');
    expect(resolveWikiSectionLabel(undefined, translate)).toBeUndefined();
    expect(resolveWikiSectionLabel('', translate)).toBeUndefined();
  });
});

describe('wikiSectionLabeler', () => {
  it('words a section the same way, so a caller can hand it on as the wording to use', () => {
    const label = wikiSectionLabeler(translate);

    expect(label('index_routing')).toBe('<kb_section_index_routing>');
    expect(label('Rollback')).toBe('Rollback');
  });
});
