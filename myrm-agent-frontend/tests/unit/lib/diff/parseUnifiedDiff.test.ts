import { describe, it, expect } from 'vitest';

import {
  parseUnifiedDiff,
  buildSplitPairs,
  inferLanguage,
  type DiffLine,
} from '@/lib/diff/parseUnifiedDiff';

describe('parseUnifiedDiff', () => {
  it('returns empty result for empty string', () => {
    const result = parseUnifiedDiff('');
    expect(result.filePath).toBe('');
    expect(result.hunks).toHaveLength(0);
    expect(result.additions).toBe(0);
    expect(result.deletions).toBe(0);
    expect(result.isBinary).toBe(false);
    expect(result.isNewFile).toBe(false);
    expect(result.isDeletedFile).toBe(false);
  });

  it('parses a simple unified diff with additions and deletions', () => {
    const diff = `diff --git a/foo.ts b/foo.ts
--- a/foo.ts
+++ b/foo.ts
@@ -1,3 +1,3 @@
 const a = 1;
-const b = 2;
+const b = 3;
 const c = 4;`;

    const result = parseUnifiedDiff(diff);
    expect(result.filePath).toBe('foo.ts');
    expect(result.hunks).toHaveLength(1);
    expect(result.additions).toBe(1);
    expect(result.deletions).toBe(1);

    const lines = result.hunks[0].lines;
    expect(lines[0].type).toBe('header');
    expect(lines[1].type).toBe('context');
    expect(lines[1].content).toBe('const a = 1;');
    expect(lines[2].type).toBe('deletion');
    expect(lines[2].content).toBe('const b = 2;');
    expect(lines[2].oldLineNumber).toBe(2);
    expect(lines[3].type).toBe('addition');
    expect(lines[3].content).toBe('const b = 3;');
    expect(lines[3].newLineNumber).toBe(2);
    expect(lines[4].type).toBe('context');
  });

  it('handles CRLF line endings', () => {
    const diff = "diff --git a/f.ts b/f.ts\r\n--- a/f.ts\r\n+++ b/f.ts\r\n@@ -1,2 +1,2 @@\r\n-old\r\n+new\r\n ctx\r\n";
    const result = parseUnifiedDiff(diff);
    expect(result.additions).toBe(1);
    expect(result.deletions).toBe(1);
  });

  it('detects binary file', () => {
    const diff = 'Binary files a/image.png and b/image.png differ';
    const result = parseUnifiedDiff(diff);
    expect(result.isBinary).toBe(true);
  });

  it('detects new file', () => {
    const diff = `diff --git a/new.ts b/new.ts
new file mode 100644
--- /dev/null
+++ b/new.ts
@@ -0,0 +1,2 @@
+line1
+line2`;

    const result = parseUnifiedDiff(diff);
    expect(result.isNewFile).toBe(true);
    expect(result.filePath).toBe('new.ts');
    expect(result.additions).toBe(2);
  });

  it('detects deleted file', () => {
    const diff = `diff --git a/old.ts b/old.ts
deleted file mode 100644
--- a/old.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2`;

    const result = parseUnifiedDiff(diff);
    expect(result.isDeletedFile).toBe(true);
    expect(result.filePath).toBe('old.ts');
    expect(result.deletions).toBe(2);
  });

  it('parses multiple hunks', () => {
    const diff = `diff --git a/f.ts b/f.ts
--- a/f.ts
+++ b/f.ts
@@ -1,3 +1,3 @@
 a
-b
+B
 c
@@ -10,3 +10,3 @@
 x
-y
+Y
 z`;

    const result = parseUnifiedDiff(diff);
    expect(result.hunks).toHaveLength(2);
    expect(result.additions).toBe(2);
    expect(result.deletions).toBe(2);
  });

  it('handles additions-only diff (no deletions)', () => {
    const diff = `diff --git a/f.ts b/f.ts
--- a/f.ts
+++ b/f.ts
@@ -1,2 +1,4 @@
 line1
+inserted1
+inserted2
 line2`;

    const result = parseUnifiedDiff(diff);
    expect(result.additions).toBe(2);
    expect(result.deletions).toBe(0);
  });

  it('handles deletions-only diff (no additions)', () => {
    const diff = `diff --git a/f.ts b/f.ts
--- a/f.ts
+++ b/f.ts
@@ -1,4 +1,2 @@
 line1
-removed1
-removed2
 line2`;

    const result = parseUnifiedDiff(diff);
    expect(result.additions).toBe(0);
    expect(result.deletions).toBe(2);
  });

  it('extracts file path from +++ line when diff --git is absent', () => {
    const diff = `--- a/old.py
+++ b/new.py
@@ -1,1 +1,1 @@
-old
+new`;

    const result = parseUnifiedDiff(diff);
    expect(result.filePath).toBe('new.py');
    expect(result.oldFilePath).toBe('old.py');
    expect(result.newFilePath).toBe('new.py');
  });

  it('correctly counts line numbers across multiple context lines', () => {
    const diff = `diff --git a/f.ts b/f.ts
--- a/f.ts
+++ b/f.ts
@@ -5,5 +5,5 @@
 ctx1
 ctx2
-old
+new
 ctx3
 ctx4`;

    const result = parseUnifiedDiff(diff);
    const lines = result.hunks[0].lines;
    const deletion = lines.find(l => l.type === 'deletion');
    const addition = lines.find(l => l.type === 'addition');
    expect(deletion?.oldLineNumber).toBe(7);
    expect(addition?.newLineNumber).toBe(7);
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

  it('returns empty array for empty input', () => {
    expect(buildSplitPairs([])).toHaveLength(0);
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
    expect(inferLanguage('style.css')).toBe('css');
    expect(inferLanguage('data.json')).toBe('json');
    expect(inferLanguage('config.yaml')).toBe('yaml');
    expect(inferLanguage('config.yml')).toBe('yaml');
    expect(inferLanguage('script.sh')).toBe('bash');
    expect(inferLanguage('hello.go')).toBe('go');
    expect(inferLanguage('App.java')).toBe('java');
    expect(inferLanguage('index.html')).toBe('markup');
  });

  it('returns text for unknown extensions', () => {
    expect(inferLanguage('file.xyz')).toBe('text');
    expect(inferLanguage('Makefile')).toBe('text');
    expect(inferLanguage('no-extension')).toBe('text');
  });

  it('handles case-insensitive extensions', () => {
    expect(inferLanguage('FILE.TS')).toBe('typescript');
    expect(inferLanguage('FOO.PY')).toBe('python');
  });
});
