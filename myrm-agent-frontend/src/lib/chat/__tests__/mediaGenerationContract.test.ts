import contract from '@shared/config/media_generation_contract.json';
import { describe, expect, it } from 'vitest';

import { IMAGE_MODEL_OPTIONS } from '@/lib/utils/media';
import { mediaGeneratedEntriesOf, readMediaGeneratedEntries } from '../mediaGenerated';

// The server half is tests/unit/ai_agents/media_tools/test_media_generation_contract.py; it holds the producers to
// the same file, so a field renamed on either side turns one of the two red.
describe('media generation contract', () => {
  it('offers the image models of the engine catalog, in its order', () => {
    expect(IMAGE_MODEL_OPTIONS.map((option) => option.value)).toEqual(contract.image_models);
  });

  describe.each(contract.collector_cases)('$name', ({ tool, result, entries }) => {
    it('registers the entries the shared cases say', () => {
      expect(mediaGeneratedEntriesOf(tool, result)).toEqual(entries);
    });

    it('restores the registered entries from a saved message', () => {
      expect(readMediaGeneratedEntries(entries)).toEqual(entries);
    });
  });
});
