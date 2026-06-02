import { describe, expect, it } from 'vitest';

import {
  MemoryArchiveFileError,
  getDefaultArchiveRestoreSections,
  parseMemoryArchivePayload,
  type MemoryArchivePayload,
} from '@/services/memoryArchive';

const archivePayload = (sections: MemoryArchivePayload['manifest']['sections']): unknown => ({
  manifest: {
    format: 'myrm_memory_archive',
    version: 1,
    created_at: '2026-05-22T00:00:00Z',
    producer: 'test',
    content_redacted: true,
    sections,
  },
  data: {
    memory: {
      semantic: [{ content: 'Use SQLite.', metadata: {} }],
    },
  },
});

describe('memoryArchive client preflight', () => {
  it('parses a Myrm archive payload without losing data sections', () => {
    const parsed = parseMemoryArchivePayload(
      archivePayload([{ name: 'memory', status: 'ready', item_count: 1, warning_codes: [] }]),
    );

    expect(parsed.manifest.format).toBe('myrm_memory_archive');
    expect(parsed.manifest.sections[0]?.name).toBe('memory');
    expect(parsed.data.memory).toEqual({
      semantic: [{ content: 'Use SQLite.', metadata: {} }],
    });
  });

  it('rejects unsupported archive shapes before sending them to the server', () => {
    expect(() => parseMemoryArchivePayload({ manifest: { format: 'other' }, data: {} })).toThrow(
      MemoryArchiveFileError,
    );
  });

  it('defaults restore selection to non-empty supported sections', () => {
    const parsed = parseMemoryArchivePayload(
      archivePayload([
        { name: 'memory', status: 'ready', item_count: 3, warning_codes: [] },
        { name: 'audit', status: 'ready', item_count: 0, warning_codes: [] },
        { name: 'replay', status: 'unsupported', item_count: 2, warning_codes: [] },
      ]),
    );

    expect(getDefaultArchiveRestoreSections(parsed)).toEqual(['memory']);
  });
});
