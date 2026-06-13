/**
 * [INPUT]
 * - unified diff 格式字符串
 * - 文件路径（用于语言推断）
 *
 * [OUTPUT]
 * - parseUnifiedDiff: 解析为结构化 ParsedDiff
 * - buildSplitPairs: 将 DiffLine[] 转为 Split 视图配对数组
 * - inferLanguage: 从文件路径推断 Prism 语言标识符
 * - DiffLine / DiffHunk / ParsedDiff / SplitPair 类型
 *
 * [POS]
 * 跨 feature 共用的 unified diff 纯函数解析器与工具集。
 * 消费方：useDiffParser hook、DiffViewer 组件。
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

// --------------- Split 视图配对 ---------------

/** Split 视图的配对行 */
export interface SplitPair {
  left: DiffLine | null;
  right: DiffLine | null;
}

/**
 * 将 hunk 行列表转为 Split 配对数组。
 * 连续 deletion 与紧随其后的 addition 按位置对齐，context 行左右同时显示。
 */
export function buildSplitPairs(lines: DiffLine[]): SplitPair[] {
  const pairs: SplitPair[] = [];
  let i = 0;
  const filtered = lines.filter((l) => l.type !== 'header');

  while (i < filtered.length) {
    const line = filtered[i];

    if (line.type === 'context') {
      pairs.push({ left: line, right: line });
      i++;
      continue;
    }

    if (line.type === 'deletion') {
      const deletions: DiffLine[] = [];
      while (i < filtered.length && filtered[i].type === 'deletion') {
        deletions.push(filtered[i]);
        i++;
      }
      const additions: DiffLine[] = [];
      while (i < filtered.length && filtered[i].type === 'addition') {
        additions.push(filtered[i]);
        i++;
      }

      const maxLen = Math.max(deletions.length, additions.length);
      for (let j = 0; j < maxLen; j++) {
        pairs.push({
          left: j < deletions.length ? deletions[j] : null,
          right: j < additions.length ? additions[j] : null,
        });
      }
      continue;
    }

    if (line.type === 'addition') {
      pairs.push({ left: null, right: line });
      i++;
      continue;
    }

    i++;
  }

  return pairs;
}

// --------------- 语言推断 ---------------

const EXT_TO_LANGUAGE: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx',
  py: 'python', rs: 'rust', go: 'go', java: 'java', kt: 'kotlin',
  rb: 'ruby', css: 'css', scss: 'scss', html: 'markup', xml: 'markup',
  json: 'json', yaml: 'yaml', yml: 'yaml', md: 'markdown', sql: 'sql',
  sh: 'bash', bash: 'bash', zsh: 'bash', c: 'c', cpp: 'cpp',
  h: 'c', hpp: 'cpp', cs: 'csharp', swift: 'swift', toml: 'toml',
  lua: 'lua', r: 'r', php: 'php', dart: 'dart',
};

/** 从文件路径推断 Prism 支持的语言标识符 */
export function inferLanguage(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  return EXT_TO_LANGUAGE[ext] ?? 'text';
}
