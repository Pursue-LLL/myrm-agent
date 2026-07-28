/**
 * [INPUT]
 * - lib/diff/parseUnifiedDiff::parseUnifiedDiff (POS: 跨 feature 共用的 unified diff 纯函数解析器)
 * - unified diff 格式字符串（Hook 参数）
 *
 * [OUTPUT]
 * - useDiffParser: memoized ParsedDiff
 *
 * [POS]
 * 跨 feature 共用的 diff 解析 Hook（cli-visualization、markdown-render-tools）。
 */

import { useMemo } from 'react';

import {
  parseUnifiedDiff,
  type DiffHunk,
  type DiffLine,
  type DiffLineType,
  type ParsedDiff,
} from '@/lib/diff/parseUnifiedDiff';

export type { DiffHunk, DiffLine, DiffLineType, ParsedDiff };

export function useDiffParser(diff: string): ParsedDiff {
  return useMemo(() => parseUnifiedDiff(diff), [diff]);
}
