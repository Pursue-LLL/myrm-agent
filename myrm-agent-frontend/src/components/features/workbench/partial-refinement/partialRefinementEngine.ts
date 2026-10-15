import { SelectionRange } from './workbenchTypes';

export function validateSelectionOffsets(
  fullText: string,
  start: number,
  end: number
): boolean {
  if (start < 0 || end < 0) {
    return false;
  }
  if (start >= end) {
    return false;
  }
  if (end > fullText.length) {
    return false;
  }
  return true;
}

export function extractSelectionWithContext(
  fullText: string,
  start: number,
  end: number,
  contextRadius = 40
): SelectionRange {
  const safeStart = Math.max(0, Math.min(start, fullText.length));
  const safeEnd = Math.max(safeStart, Math.min(end, fullText.length));

  const selectedText = fullText.slice(safeStart, safeEnd);
  const contextBefore = fullText.slice(
    Math.max(0, safeStart - contextRadius),
    safeStart
  );
  const contextAfter = fullText.slice(
    safeEnd,
    Math.min(fullText.length, safeEnd + contextRadius)
  );

  return {
    startOffset: safeStart,
    endOffset: safeEnd,
    selectedText,
    contextBefore,
    contextAfter,
  };
}

export function applyInPlaceReplacement(
  fullText: string,
  range: SelectionRange,
  replacementText: string
): string {
  const { startOffset, endOffset } = range;
  if (!validateSelectionOffsets(fullText, startOffset, endOffset)) {
    // If range is out of bounds or invalid, fall back to exact substring replacement if found
    if (range.selectedText && fullText.includes(range.selectedText)) {
      return fullText.replace(range.selectedText, replacementText);
    }
    return fullText;
  }

  const prefix = fullText.slice(0, startOffset);
  const suffix = fullText.slice(endOffset);
  return `${prefix}${replacementText}${suffix}`;
}

export interface TokenSavingsEstimate {
  fullTokens: number;
  chunkTokens: number;
  tokensSaved: number;
  savingsPercent: number;
}

export function estimateTokenSavings(
  fullTextLength: number,
  chunkLength: number
): TokenSavingsEstimate {
  // Approximate standard ratio: 1 token ≈ 4 characters
  const fullTokens = Math.max(1, Math.round(fullTextLength / 4));
  const chunkTokens = Math.max(1, Math.round(chunkLength / 4));
  const tokensSaved = Math.max(0, fullTokens - chunkTokens);
  const savingsPercent = Math.min(
    99,
    Math.max(0, Math.round((tokensSaved / fullTokens) * 100))
  );

  return {
    fullTokens,
    chunkTokens,
    tokensSaved,
    savingsPercent,
  };
}

export function generateSimulatedRefinement(
  originalChunk: string,
  instruction: string
): string {
  const trimmed = instruction.trim();
  if (!trimmed) {
    return originalChunk;
  }

  if (trimmed.includes('保守估值') || trimmed.includes('风险')) {
    return originalChunk
      .replace(/高增长|激进|极速/g, '稳健增长')
      .concat('\n> 补充汇率与地缘风险防范准备金：按5%提取。');
  }

  if (trimmed.includes('简明') || trimmed.includes('精炼')) {
    return originalChunk
      .split('\n')
      .filter((line) => line.trim().length > 0)
      .slice(0, 3)
      .join('\n');
  }

  if (trimmed.includes('加粗') || trimmed.includes('强调')) {
    return `**${originalChunk.trim()}**`;
  }

  return `[已就地精修: ${trimmed}]\n${originalChunk}`;
}
