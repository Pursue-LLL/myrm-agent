/**
 * Exact anchor machine symbols parser for context compaction summary.
 *
 * [INPUT]
 * - CompactionAnchorStrip::ExactAnchorData (POS: Exact anchor machine symbols data contract)
 * - summaryText: Raw markdown compaction summary string
 * - metaAnchors?: Structured metadata anchor payload
 *
 * [OUTPUT]
 * - parseExactAnchors: Pure functional parser extracting exact machine symbols and cleaning markdown
 *
 * [POS]
 * Context compaction parser utility for deterministic anchor symbol extraction.
 */

import type { ExactAnchorData } from './CompactionAnchorStrip';

export interface ParseExactAnchorsResult {
  anchors: ExactAnchorData;
  cleanedSummary: string;
}

const EMPTY_ANCHORS: ExactAnchorData = {
  commitShas: [],
  filePaths: [],
  errorSpans: [],
  codeSymbols: [],
  apiEndpoints: [],
};

const JSON_ANCHOR_REGEX = /<!--\s*EXACT_ANCHOR_JSON:\s*(\{[\s\S]*?\})\s*-->/;
const MARKDOWN_ANCHOR_BLOCK_REGEX =
  /(?:^|\n)(?:#{2,4}\s+⚓\s+Exact Anchor Index|\[Verified Exact Anchors[^\n\]]*\])[^\n]*\n([\s\S]*?)(?=(?:\n#{1,4}\s+[^⚓]|\n<preserve_context>|$))/i;

function extractBacktickItems(line: string): string[] {
  const matches: string[] = [];
  const regex = /`([^`]+)`/g;
  let match: RegExpExecArray | null = regex.exec(line);
  while (match !== null) {
    const val = match[1]?.trim();
    if (val) {
      matches.push(val);
    }
    match = regex.exec(line);
  }
  return matches;
}

/**
 * Parses exact anchor machine symbols from compaction summary markdown or metadata.
 * Strips the raw markdown symbol block when extracted so the visual strip does not duplicate text.
 */
export function parseExactAnchors(summaryText: string, metaAnchors?: ExactAnchorData | null): ParseExactAnchorsResult {
  if (metaAnchors && Object.values(metaAnchors).some((arr) => Array.isArray(arr) && arr.length > 0)) {
    return {
      anchors: {
        commitShas: metaAnchors.commitShas ?? [],
        filePaths: metaAnchors.filePaths ?? [],
        errorSpans: metaAnchors.errorSpans ?? [],
        codeSymbols: metaAnchors.codeSymbols ?? [],
        apiEndpoints: metaAnchors.apiEndpoints ?? [],
      },
      cleanedSummary: summaryText,
    };
  }

  if (!summaryText) {
    return { anchors: EMPTY_ANCHORS, cleanedSummary: '' };
  }

  // 1. Try JSON metadata block if present
  const jsonMatch = JSON_ANCHOR_REGEX.exec(summaryText);
  if (jsonMatch && jsonMatch[1]) {
    try {
      const parsed = JSON.parse(jsonMatch[1]) as Record<string, unknown>;
      const anchors: ExactAnchorData = {
        commitShas: Array.isArray(parsed.commit_shas) ? (parsed.commit_shas as string[]) : [],
        filePaths: Array.isArray(parsed.file_paths) ? (parsed.file_paths as string[]) : [],
        errorSpans: Array.isArray(parsed.error_spans) ? (parsed.error_spans as string[]) : [],
        codeSymbols: Array.isArray(parsed.code_symbols) ? (parsed.code_symbols as string[]) : [],
        apiEndpoints: Array.isArray(parsed.api_endpoints) ? (parsed.api_endpoints as string[]) : [],
      };
      const cleanedSummary = summaryText.replace(JSON_ANCHOR_REGEX, '').replace(MARKDOWN_ANCHOR_BLOCK_REGEX, '').trim();
      return { anchors, cleanedSummary };
    } catch {
      // Fallback to markdown parsing
    }
  }

  // 2. Try Markdown block: ### ⚓ Exact Anchor Index (Deterministic Machine Symbols)
  const mdMatch = MARKDOWN_ANCHOR_BLOCK_REGEX.exec(summaryText);
  if (!mdMatch) {
    return { anchors: EMPTY_ANCHORS, cleanedSummary: summaryText };
  }

  const blockBody = mdMatch[1] || '';
  const lines = blockBody.split('\n');

  const commitShas: string[] = [];
  const filePaths: string[] = [];
  const codeSymbols: string[] = [];
  const apiEndpoints: string[] = [];
  const errorSpans: string[] = [];

  let inErrorsSection = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }

    const isSectionHeader = /^\s*[-*]\s*\*\*/.test(rawLine);
    if (isSectionHeader) {
      if (/commits?/i.test(line)) {
        inErrorsSection = false;
        commitShas.push(...extractBacktickItems(line));
      } else if (/(?:files?|paths?)/i.test(line)) {
        inErrorsSection = false;
        filePaths.push(...extractBacktickItems(line));
      } else if (/symbols?/i.test(line)) {
        inErrorsSection = false;
        codeSymbols.push(...extractBacktickItems(line));
      } else if (/endpoints?/i.test(line)) {
        inErrorsSection = false;
        apiEndpoints.push(...extractBacktickItems(line));
      } else if (/errors?/i.test(line)) {
        inErrorsSection = true;
        errorSpans.push(...extractBacktickItems(line));
      }
    } else if (inErrorsSection) {
      if (line.startsWith('*') || line.startsWith('-')) {
        const items = extractBacktickItems(line);
        if (items.length > 0) {
          errorSpans.push(...items);
        }
      } else {
        inErrorsSection = false;
      }
    }
  }

  const cleanedSummary = summaryText.replace(MARKDOWN_ANCHOR_BLOCK_REGEX, '').trim();

  return {
    anchors: {
      commitShas,
      filePaths,
      errorSpans,
      codeSymbols,
      apiEndpoints,
    },
    cleanedSummary,
  };
}
