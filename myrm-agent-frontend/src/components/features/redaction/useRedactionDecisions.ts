import { useCallback, useState } from 'react';

import type { RedactionResponse } from '@/services/skill';

export type RedactionFindings = Record<string, RedactionResponse[]>;

/** File path -> indices of findings the author chose to keep as written. */
export type IgnoredRedactions = Record<string, number[]>;

/** Decisions that keep every finding as written ("export original"). */
export function keepEveryFinding(findings: RedactionFindings): IgnoredRedactions {
  return Object.fromEntries(Object.entries(findings).map(([path, items]) => [path, items.map((_, index) => index)]));
}

/** Decisions that actually keep something; an empty map means "redact everything". */
export function hasKeptFindings(ignored: IgnoredRedactions): boolean {
  return Object.values(ignored).some((indices) => indices.length > 0);
}

/**
 * Review state shared by every export dialog: findings are redacted unless the author
 * explicitly keeps them. Decisions belong to one preview, so callers reset on reload.
 */
export function useRedactionDecisions() {
  const [ignored, setIgnored] = useState<IgnoredRedactions>({});

  const reset = useCallback(() => setIgnored({}), []);

  const toggle = useCallback((path: string, index: number) => {
    setIgnored((prev) => {
      const kept = prev[path] ?? [];
      return { ...prev, [path]: kept.includes(index) ? kept.filter((i) => i !== index) : [...kept, index] };
    });
  }, []);

  /** Keeps every finding of a file when none is kept yet; otherwise redacts them all again. */
  const toggleAll = useCallback((path: string, total: number) => {
    setIgnored((prev) => {
      const noneKept = (prev[path] ?? []).length === 0;
      return { ...prev, [path]: noneKept ? Array.from({ length: total }, (_, index) => index) : [] };
    });
  }, []);

  return { ignored, reset, toggle, toggleAll };
}
