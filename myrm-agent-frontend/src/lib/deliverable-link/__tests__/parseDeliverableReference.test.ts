import { describe, expect, it } from 'vitest';
import {
  looksLikeWorkspacePath,
  normalizeWorkspaceBrowsePath,
  parseDeliverableReference,
} from '@/lib/deliverable-link/parseDeliverableReference';

describe('parseDeliverableReference', () => {
  it('parses workspace/ prefixed paths', () => {
    expect(parseDeliverableReference('workspace/reports/q1-summary.md')).toEqual({
      kind: 'workspace',
      path: 'workspace/reports/q1-summary.md',
    });
  });

  it('parses relative paths with extension', () => {
    expect(parseDeliverableReference('output/brief.pdf')).toEqual({
      kind: 'workspace',
      path: 'output/brief.pdf',
    });
  });

  it('parses artifact: protocol', () => {
    expect(parseDeliverableReference('artifact:abc-123')).toEqual({
      kind: 'artifact',
      id: 'abc-123',
    });
  });

  it('parses @file_ harness aliases', () => {
    expect(parseDeliverableReference('@file_001')).toEqual({
      kind: 'file_id',
      id: '@file_001',
    });
  });

  it('ignores bare words and URLs', () => {
    expect(parseDeliverableReference('config')).toBeNull();
    expect(parseDeliverableReference('https://example.com/a.md')).toBeNull();
  });
});

describe('looksLikeWorkspacePath', () => {
  it('requires slash or extension', () => {
    expect(looksLikeWorkspacePath('notes/todo.md')).toBe(true);
    expect(looksLikeWorkspacePath('readme.txt')).toBe(true);
    expect(looksLikeWorkspacePath('foo')).toBe(false);
  });
});

describe('normalizeWorkspaceBrowsePath', () => {
  it('strips workspace/ prefix for browse API', () => {
    expect(normalizeWorkspaceBrowsePath('workspace/a/b.md')).toBe('a/b.md');
    expect(normalizeWorkspaceBrowsePath('a/b.md')).toBe('a/b.md');
  });
});
