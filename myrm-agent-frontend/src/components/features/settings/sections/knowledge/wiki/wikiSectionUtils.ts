'use client';

/**
 * [INPUT] comma-separated tag/alias input strings
 * [OUTPUT] splitTagsInput
 * [POS] Settings wiki metadata editor helpers (list parsing lives on server SSOT)
 */

export function splitTagsInput(raw: string): string[] {
  return raw
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}
