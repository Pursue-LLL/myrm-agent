import { describe, expect, it } from 'vitest';
import { isCoverImageSuggestion } from './useWechatCoverSuggest';
import type { ReferenceSuggestion } from '@/services/chat';

function makeSuggestion(overrides: Partial<ReferenceSuggestion>): ReferenceSuggestion {
  return {
    source: 'workspace',
    reference_type: 'workspace_file',
    kind: 'file',
    label: 'cover.png',
    basename: 'cover.png',
    directory: 'images',
    relative_path: 'images/cover.png',
    file_id: null,
    description: null,
    size: 1024,
    score_tier: 'prefix',
    score: 100,
    match_ranges: [],
    ...overrides,
  };
}

describe('isCoverImageSuggestion', () => {
  it('accepts common raster image extensions', () => {
    expect(isCoverImageSuggestion(makeSuggestion({ basename: 'hero.webp', relative_path: 'hero.webp' }))).toBe(true);
  });

  it('rejects non-image files and missing paths', () => {
    expect(isCoverImageSuggestion(makeSuggestion({ basename: 'readme.md', relative_path: 'readme.md' }))).toBe(false);
    expect(isCoverImageSuggestion(makeSuggestion({ relative_path: null }))).toBe(false);
    expect(isCoverImageSuggestion(makeSuggestion({ kind: 'directory' }))).toBe(false);
  });
});
