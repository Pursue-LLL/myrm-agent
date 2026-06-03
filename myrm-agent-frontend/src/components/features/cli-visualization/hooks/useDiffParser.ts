/**
 * Diff 解析 Hook
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md
 *
 * [INPUT]
 * - unified diff 格式字符串
 *
 * [OUTPUT]
 * - useDiffParser: 解析 unified diff 为结构化数据
 *   - filePath: 文件路径
 *   - hunks: diff 块列表
 *   - additions: 新增行数
 *   - deletions: 删除行数
 *
 * [POS]
 * CLI 可视化工具的 Diff 解析 Hook。将 unified diff 格式
 * 解析为结构化数据，供 CLIDiffViewer 渲染。
 */

import { useMemo } from 'react';

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

/**
 * 解析 unified diff 格式
 */
function parseUnifiedDiff(diff: string): ParsedDiff {
  const lines = diff.split('\n');
  const result: ParsedDiff = {
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

  let currentHunk: DiffHunk | null = null;
  let oldLineNumber = 0;
  let newLineNumber = 0;

  for (const line of lines) {
    // 解析 diff --git 行
    if (line.startsWith('diff --git')) {
      const match = line.match(/diff --git a\/(.+) b\/(.+)/);
      if (match) {
        result.oldFilePath = match[1];
        result.newFilePath = match[2];
        result.filePath = match[2];
      }
      continue;
    }

    // 检测新文件
    if (line.startsWith('new file mode')) {
      result.isNewFile = true;
      continue;
    }

    // 检测删除文件
    if (line.startsWith('deleted file mode')) {
      result.isDeletedFile = true;
      continue;
    }

    // 检测二进制文件
    if (line.includes('Binary files')) {
      result.isBinary = true;
      continue;
    }

    // 解析 --- 行
    if (line.startsWith('---')) {
      const match = line.match(/^--- (?:a\/)?(.+)$/);
      if (match) {
        result.oldFilePath = match[1];
      }
      continue;
    }

    // 解析 +++ 行
    if (line.startsWith('+++')) {
      const match = line.match(/^\+\+\+ (?:b\/)?(.+)$/);
      if (match) {
        result.newFilePath = match[1];
        result.filePath = match[1];
      }
      continue;
    }

    // 解析 hunk header (@@ ... @@)
    if (line.startsWith('@@')) {
      // 保存之前的 hunk
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

        // 添加 header 行
        currentHunk.lines.push({
          type: 'header',
          content: line,
          oldLineNumber: null,
          newLineNumber: null,
        });
      }
      continue;
    }

    // 解析 diff 内容行
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

  // 保存最后一个 hunk
  if (currentHunk) {
    result.hunks.push(currentHunk);
  }

  return result;
}

/**
 * Diff 解析 Hook
 *
 * @param diff - unified diff 格式字符串
 * @returns 解析后的结构化 diff 数据
 */
export function useDiffParser(diff: string): ParsedDiff {
  return useMemo(() => {
    if (!diff) {
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
    return parseUnifiedDiff(diff);
  }, [diff]);
}

export default useDiffParser;
