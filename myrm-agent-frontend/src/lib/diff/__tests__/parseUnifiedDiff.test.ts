import { describe, expect, it } from 'vitest';

import { parseUnifiedDiff } from '../parseUnifiedDiff';

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
