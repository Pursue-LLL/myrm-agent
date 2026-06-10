/**
 * [INPUT]
 * - unified diff 格式字符串
 *
 * [OUTPUT]
 * - parseUnifiedDiff: 解析为结构化 ParsedDiff
 * - DiffLine / DiffHunk / ParsedDiff 类型
 *
 * [POS]
 * 跨 feature 共用的 unified diff 纯函数解析器（cli-visualization、markdown-render-tools）。
 */

/** Diff 行类型 */
export type DiffLineType = 'context' | 'addition' | 'deletion' | 'header';

/** 单行 Diff 数据 */
export interface DiffLine {
  type: DiffLineType;
  content: string;
  oldLineNumber: number | null;
  newLineNumber: number | null;
}

/** Diff 块 */
export interface DiffHunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
}

/** 解析后的 Diff 结果 */
export interface ParsedDiff {
  filePath: string;
  oldFilePath: string | null;
  newFilePath: string | null;
  hunks: DiffHunk[];
  additions: number;
  deletions: number;
  isNewFile: boolean;
  isDeletedFile: boolean;
  isBinary: boolean;
}

function createEmptyParsedDiff(): ParsedDiff {
  return {
    filePath: '',
    oldFilePath: null,
    newFilePath: null,
    hunks: [],
    additions: 0,
    deletions: 0,
    isNewFile: false,
    isDeletedFile: false,
    isBinary: false,
  };
}

/** 解析 unified diff 格式 */
export function parseUnifiedDiff(diff: string): ParsedDiff {
  if (!diff) {
    return createEmptyParsedDiff();
  }

  const lines = diff.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const result = createEmptyParsedDiff();

  let currentHunk: DiffHunk | null = null;
  let oldLineNumber = 0;
  let newLineNumber = 0;

  for (const line of lines) {
    if (line.startsWith('diff --git')) {
      const match = line.match(/diff --git a\/(.+) b\/(.+)/);
      if (match) {
        result.oldFilePath = match[1];
        result.newFilePath = match[2];
        result.filePath = match[2];
      }
      continue;
    }

    if (line.startsWith('new file mode')) {
      result.isNewFile = true;
      continue;
    }

    if (line.startsWith('deleted file mode')) {
      result.isDeletedFile = true;
      continue;
    }

    if (line.includes('Binary files')) {
      result.isBinary = true;
      continue;
    }

    if (line.startsWith('---')) {
      const match = line.match(/^--- (?:a\/)?(.+)$/);
      if (match) {
        result.oldFilePath = match[1];
      }
      continue;
    }

    if (line.startsWith('+++')) {
      const match = line.match(/^\+\+\+ (?:b\/)?(.+)$/);
      if (match) {
        const newPath = match[1];
        result.newFilePath = newPath;
        result.filePath =
          newPath === '/dev/null' && result.oldFilePath ? result.oldFilePath : newPath;
      }
      continue;
    }

    if (line.startsWith('@@')) {
      if (currentHunk) {
        result.hunks.push(currentHunk);
      }

      const match = line.match(/@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
      if (match) {
        currentHunk = {
          oldStart: parseInt(match[1], 10),
          oldLines: parseInt(match[2] || '1', 10),
          newStart: parseInt(match[3], 10),
          newLines: parseInt(match[4] || '1', 10),
          lines: [],
        };
        oldLineNumber = currentHunk.oldStart;
        newLineNumber = currentHunk.newStart;

        currentHunk.lines.push({
          type: 'header',
          content: line,
          oldLineNumber: null,
          newLineNumber: null,
        });
      }
      continue;
    }

    if (currentHunk) {
      if (line.startsWith('+')) {
        currentHunk.lines.push({
          type: 'addition',
          content: line.slice(1),
          oldLineNumber: null,
          newLineNumber: newLineNumber++,
        });
        result.additions++;
      } else if (line.startsWith('-')) {
        currentHunk.lines.push({
          type: 'deletion',
          content: line.slice(1),
          oldLineNumber: oldLineNumber++,
          newLineNumber: null,
        });
        result.deletions++;
      } else if (line.startsWith(' ') || line === '') {
        currentHunk.lines.push({
          type: 'context',
          content: line.slice(1) || '',
          oldLineNumber: oldLineNumber++,
          newLineNumber: newLineNumber++,
        });
      }
    }
  }

  if (currentHunk) {
    result.hunks.push(currentHunk);
  }

  return result;
}
