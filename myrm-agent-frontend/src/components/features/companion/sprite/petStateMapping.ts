/**
 * petStateMapping — Dynamic spritesheet row taxonomy for Codex/Legacy pet assets.
 *
 * [INPUT]
 * - PetState (POS: Internal animation state enum from PetStateMachine)
 *
 * [OUTPUT]
 * - resolvePetSheetRow: Maps PetState → actual spritesheet row index for any sheet layout
 *
 * [POS]
 * Translates PetStateMachine's PetState enum to actual spritesheet row indices.
 * Handles two atlas formats (Codex 9-row, Legacy 8-row) and resolves via text aliases
 * so community spritesheets with varying row taxonomies render correctly.
 */

import { PetState } from './PetStateMachine';

/**
 * Current Petdex/Codex row order (top → bottom) for 8×9 atlases (1536×1872px).
 * Source: petdex.dev Codex standard.
 */
const CODEX_STATE_ROWS: readonly string[] = [
  'idle',
  'running-right',
  'running-left',
  'waving',
  'jumping',
  'failed',
  'waiting',
  'running',
  'review',
] as const;

/**
 * Legacy Hermes/Petdex row order for older 9×8 atlases (1728×1664px).
 */
const LEGACY_STATE_ROWS: readonly string[] = [
  'idle',
  'wave',
  'run',
  'failed',
  'review',
  'jump',
  'extra1',
  'extra2',
] as const;

/**
 * Maps PetState to accepted spritesheet row name aliases (Codex + Legacy naming).
 */
const PET_STATE_ALIASES: Record<PetState, readonly string[]> = {
  [PetState.IDLE]: ['idle'],
  [PetState.RUNNING]: ['running', 'running-right', 'run'],
  [PetState.REVIEWING]: ['review'],
  [PetState.JUMP]: ['jumping', 'jump'],
  [PetState.WAVE]: ['waving', 'wave'],
  [PetState.FAILED]: ['failed'],
  [PetState.WAITING]: ['waiting', 'idle'],
};

function stateRowsForGrid(rowCount: number): readonly string[] {
  return rowCount >= CODEX_STATE_ROWS.length ? CODEX_STATE_ROWS : LEGACY_STATE_ROWS;
}

/**
 * Resolve the actual spritesheet row index for a given PetState.
 *
 * @param petState  Internal animation state from PetStateMachine
 * @param sheetRows  Number of rows detected in the loaded spritesheet
 * @returns 0-indexed row in the spritesheet (falls back to 0/idle on no match)
 */
export function resolvePetSheetRow(petState: PetState, sheetRows: number): number {
  const taxonomy = stateRowsForGrid(sheetRows);
  const aliases = PET_STATE_ALIASES[petState];

  for (const alias of aliases) {
    const idx = taxonomy.indexOf(alias);
    if (idx !== -1 && idx < sheetRows) return idx;
  }

  return 0;
}
