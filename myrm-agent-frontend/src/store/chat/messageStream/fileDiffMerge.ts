/**
 * [OUTPUT]
 * FILE_DIFF merge helpers: path matching, diff richness scoring, pickMergedFileDiffPayload
 *
 * [POS]
 * Unified diff merge logic for progressSteps file rows during agent streaming.
 */

import type { ProgressFileItem } from './types';

export function parseProgressFilePath(item: unknown): string | undefined {
  if (!item || typeof item !== 'object' || !('file_path' in item)) return undefined;
  const fp = (item as { file_path?: unknown }).file_path;
  return typeof fp === 'string' ? fp : undefined;
}

export function pathsMatchForFileDiff(diffPath: string, itemPath: string): boolean {
  return itemPath === diffPath || diffPath.endsWith(itemPath) || itemPath.endsWith(diffPath);
}

/** Prefer richer unified diffs when merging FILE_DIFF bursts (weak “from /dev/null” must not overwrite str_replace). */
export function scoreUnifiedDiffForMerge(diff: string): number {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
  }
  let score = 0;
  if (hasMinus && hasPlus) score += 100;
  else if (hasMinus || hasPlus) score += 10;
  if (diff.includes('@@')) score += 5;
  score += Math.min(diff.length, 500_000) / 50_000;
  return score;
}

function diffHasMinusAndPlusLinesMerge(diff: string): boolean {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
    if (hasMinus && hasPlus) return true;
  }
  return false;
}

export function pickMergedFileDiffPayload(
  current: { diff?: string; diff_truncated?: boolean },
  incomingDiff: string,
  incomingTruncated: boolean,
): { diff: string; diff_truncated: boolean } {
  const cur = current.diff;
  if (!cur) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  const sc = scoreUnifiedDiffForMerge(cur);
  const si = scoreUnifiedDiffForMerge(incomingDiff);
  if (si > sc) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  if (sc > si) {
    return { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
  }
  const cm = diffHasMinusAndPlusLinesMerge(cur);
  const im = diffHasMinusAndPlusLinesMerge(incomingDiff);
  if (im && !cm) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  if (cm && !im) {
    return { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
  }
  return incomingDiff.length >= cur.length
    ? { diff: incomingDiff, diff_truncated: incomingTruncated }
    : { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
}
