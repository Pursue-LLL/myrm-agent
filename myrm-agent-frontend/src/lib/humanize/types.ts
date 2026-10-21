/**
 * Human-readable tool / approval presentation types.
 *
 * [POS] FE-only SSOT for ProgressSteps titles and approval headlines.
 */

export type TranslateFn = (key: string, values?: Record<string, string | number>) => string;

export type ApprovalSurface = 'compact' | 'full';

export type ScopeNote = {
  text: string;
  external: boolean;
};
