/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * getConsolidationUndo / undoConsolidation: read the latest auto-consolidation that can still be undone, and undo it.
 * ConsolidationUndoSummary / ConsolidationUndoResult: response DTOs.
 *
 * [POS]
 * Auto-consolidation undo client of the Personal Brain Command Center. An undo names the cycle the user was shown:
 * the server refuses it (409) once that cycle was undone or a newer one replaced it, so a stale card cannot undo another cycle.
 */

import { apiRequest } from '@/lib/api';

export interface ConsolidationUndoSummary {
  cycle_id: string;
  recorded_at: string;
  merged: number;
  corrected: number;
  updated: number;
  /** Memories the cycle created or changed; undoing it deletes the former and restores the latter. */
  change_count: number;
  /** Of those, the memories the user has since edited or removed; an undo leaves them as they are. */
  conflict_count: number;
}

export interface ConsolidationUndoResult {
  rolled_back: number;
  skipped_conflict: number;
  errors: number;
}

/** The latest consolidation cycle that can still be undone, or `null` when there is none. */
export const getConsolidationUndo = async (): Promise<ConsolidationUndoSummary | null> => {
  const state = await apiRequest<{ summary: ConsolidationUndoSummary | null }>(
    '/memory/command-center/consolidation/undo',
  );
  return state.summary;
};

export const undoConsolidation = async (cycleId: string): Promise<ConsolidationUndoResult> => {
  return apiRequest<ConsolidationUndoResult>('/memory/command-center/consolidation/undo', {
    method: 'POST',
    body: JSON.stringify({ cycle_id: cycleId }),
  });
};
