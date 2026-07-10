import { describe, expect, it } from 'vitest';

import {
  buildSplitPairs,
  inferLanguage,
  parseUnifiedDiff,
  type DiffLine,
} from '../parseUnifiedDiff';

describe('parseUnifiedDiff', () => {
  it('returns isolated empty results for blank input', () => {
    const first = parseUnifiedDiff('');
    const second = parseUnifiedDiff('');

    expect(first.hunks).toEqual([]);
    expect(second.hunks).toEqual([]);
    expect(first.hunks).not.toBe(second.hunks);
  });

  it('parses a single hunk with addition and deletion counts', () => {
    const diff = [
      'diff --git a/foo.ts b/foo.ts',
      '--- a/foo.ts',
      '+++ b/foo.ts',
      '@@ -1,2 +1,2 @@',
      '-old',
      '+new',
    ].join('\n');

    const parsed = parseUnifiedDiff(diff);

    expect(parsed.filePath).toBe('foo.ts');
    expect(parsed.hunks).toHaveLength(1);
    expect(parsed.deletions).toBe(1);
    expect(parsed.additions).toBe(1);
  });

  it('parses CRLF unified diff lines', () => {
    const diff = 'diff --git a/a.txt b/a.txt\r\n--- a/a.txt\r\n+++ b/a.txt\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n';

    const parsed = parseUnifiedDiff(diff);

    expect(parsed.filePath).toBe('a.txt');
    expect(parsed.additions).toBe(1);
    expect(parsed.deletions).toBe(1);
    const addition = parsed.hunks[0]?.lines.find((line) => line.type === 'addition');
    expect(addition?.content).toBe('new');
  });

  it('marks binary diffs without hunks', () => {
    const diff = [
      'diff --git a/image.png b/image.png',
      'Binary files a/image.png and b/image.png differ',
    ].join('\n');

    const parsed = parseUnifiedDiff(diff);

    expect(parsed.isBinary).toBe(true);
    expect(parsed.hunks).toHaveLength(0);
  });

  it('marks deleted files', () => {
    const diff = [
      'diff --git a/removed.ts b/removed.ts',
      'deleted file mode 100644',
      '--- a/removed.ts',
      '+++ /dev/null',
    ].join('\n');

    const parsed = parseUnifiedDiff(diff);

    expect(parsed.isDeletedFile).toBe(true);
    expect(parsed.newFilePath).toBe('/dev/null');
    expect(parsed.filePath).toBe('removed.ts');
  });
});

describe('buildSplitPairs', () => {
  it('pairs context lines as left+right', () => {
    const lines: DiffLine[] = [
      { type: 'context', content: 'foo', oldLineNumber: 1, newLineNumber: 1 },
    ];
    const pairs = buildSplitPairs(lines);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].left).toBe(lines[0]);
    expect(pairs[0].right).toBe(lines[0]);
  });

  it('pairs consecutive deletion+addition', () => {
    const del: DiffLine = { type: 'deletion', content: 'old', oldLineNumber: 1, newLineNumber: null };
    const add: DiffLine = { type: 'addition', content: 'new', oldLineNumber: null, newLineNumber: 1 };
    const pairs = buildSplitPairs([del, add]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].left).toBe(del);
    expect(pairs[0].right).toBe(add);
  });

  it('returns empty array for empty input', () => {
    expect(buildSplitPairs([])).toHaveLength(0);
  });

  it('handles unbalanced deletions and additions', () => {
    const del1: DiffLine = { type: 'deletion', content: 'a', oldLineNumber: 1, newLineNumber: null };
    const del2: DiffLine = { type: 'deletion', content: 'b', oldLineNumber: 2, newLineNumber: null };
    const add1: DiffLine = { type: 'addition', content: 'x', oldLineNumber: null, newLineNumber: 1 };

    const pairs = buildSplitPairs([del1, del2, add1]);
    expect(pairs).toHaveLength(2);
    expect(pairs[0].left).toBe(del1);
    expect(pairs[0].right).toBe(add1);
    expect(pairs[1].left).toBe(del2);
    expect(pairs[1].right).toBeNull();
  });

  it('places standalone addition on right side', () => {
    const add: DiffLine = { type: 'addition', content: 'new', oldLineNumber: null, newLineNumber: 5 };
    const pairs = buildSplitPairs([add]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].left).toBeNull();
    expect(pairs[0].right).toBe(add);
  });

  it('skips header lines', () => {
    const header: DiffLine = { type: 'header', content: '@@ -1,3 +1,3 @@', oldLineNumber: null, newLineNumber: null };
    const ctx: DiffLine = { type: 'context', content: 'x', oldLineNumber: 1, newLineNumber: 1 };
    const pairs = buildSplitPairs([header, ctx]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].left).toBe(ctx);
  });

  it('handles more additions than deletions', () => {
    const del: DiffLine = { type: 'deletion', content: 'a', oldLineNumber: 1, newLineNumber: null };
    const add1: DiffLine = { type: 'addition', content: 'x', oldLineNumber: null, newLineNumber: 1 };
    const add2: DiffLine = { type: 'addition', content: 'y', oldLineNumber: null, newLineNumber: 2 };

    const pairs = buildSplitPairs([del, add1, add2]);
    expect(pairs).toHaveLength(2);
    expect(pairs[0].left).toBe(del);
    expect(pairs[0].right).toBe(add1);
    expect(pairs[1].left).toBeNull();
    expect(pairs[1].right).toBe(add2);
  });

  it('handles mixed context and modifications', () => {
    const ctx1: DiffLine = { type: 'context', content: 'a', oldLineNumber: 1, newLineNumber: 1 };
    const del: DiffLine = { type: 'deletion', content: 'b', oldLineNumber: 2, newLineNumber: null };
    const add: DiffLine = { type: 'addition', content: 'B', oldLineNumber: null, newLineNumber: 2 };
    const ctx2: DiffLine = { type: 'context', content: 'c', oldLineNumber: 3, newLineNumber: 3 };

    const pairs = buildSplitPairs([ctx1, del, add, ctx2]);
    expect(pairs).toHaveLength(3);
    expect(pairs[0].left).toBe(ctx1);
    expect(pairs[0].right).toBe(ctx1);
    expect(pairs[1].left).toBe(del);
    expect(pairs[1].right).toBe(add);
    expect(pairs[2].left).toBe(ctx2);
    expect(pairs[2].right).toBe(ctx2);
  });
});

describe('inferLanguage', () => {
  it('maps known extensions', () => {
    expect(inferLanguage('app/foo.ts')).toBe('typescript');
    expect(inferLanguage('foo.tsx')).toBe('tsx');
    expect(inferLanguage('bar.py')).toBe('python');
    expect(inferLanguage('main.rs')).toBe('rust');
    expect(inferLanguage('index.html')).toBe('markup');
    expect(inferLanguage('data.json')).toBe('json');
    expect(inferLanguage('config.yaml')).toBe('yaml');
  });

  it('returns text for unknown extensions', () => {
    expect(inferLanguage('file.xyz')).toBe('text');
    expect(inferLanguage('Makefile')).toBe('text');
  });

  it('handles case-insensitive extensions', () => {
    expect(inferLanguage('FILE.TS')).toBe('typescript');
    expect(inferLanguage('FOO.PY')).toBe('python');
  });
});
