/**
 * petStateMapping — Dynamic spritesheet row taxonomy for Codex/Legacy pet assets.
 *
 * [INPUT]
 * - AnimRow (POS: Internal animation state enum from PetStateMachine)
 *
 * [OUTPUT]
 * - resolveAnimRow: Maps AnimRow → actual spritesheet row index for any sheet layout
 *
 * [POS]
 * Translates PetStateMachine's internal AnimRow enum to actual spritesheet row indices.
 * Handles two atlas formats (Codex 9-row, Legacy 8-row) and resolves via text aliases
 * so community spritesheets with varying row taxonomies render correctly.
 */

import { AnimRow } from './PetStateMachine';

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
 * Maps our internal AnimRow states to accepted spritesheet row name aliases,
 * in descending preference. Covers both Codex naming (waving, jumping, running)
 * and Legacy naming (wave, jump, run).
 */
const ANIM_ROW_ALIASES: Record<AnimRow, readonly string[]> = {
  [AnimRow.IDLE]: ['idle'],
  [AnimRow.RUNNING]: ['running', 'running-right', 'run'],
  [AnimRow.SLEEPING]: ['idle'],
  [AnimRow.CODING]: ['running', 'run'],
  [AnimRow.THINKING]: ['review', 'waiting'],
  [AnimRow.CELEBRATING]: ['jumping', 'jump', 'waving', 'wave'],
  [AnimRow.FAILED]: ['failed'],
  [AnimRow.REVIEWING]: ['review', 'waiting'],
  [AnimRow.WAVING]: ['waving', 'wave'],
};

function stateRowsForGrid(rowCount: number): readonly string[] {
  return rowCount >= CODEX_STATE_ROWS.length ? CODEX_STATE_ROWS : LEGACY_STATE_ROWS;
}

/**
 * Resolve the actual spritesheet row index for a given AnimRow state.
 *
 * @param animRow  Internal animation state from PetStateMachine
 * @param sheetRows  Number of rows detected in the loaded spritesheet
 * @returns 0-indexed row in the spritesheet (falls back to 0/idle on no match)
 */
export function resolveAnimRow(animRow: AnimRow, sheetRows: number): number {
  const taxonomy = stateRowsForGrid(sheetRows);
  const aliases = ANIM_ROW_ALIASES[animRow];

  for (const alias of aliases) {
    const idx = taxonomy.indexOf(alias);
    if (idx !== -1 && idx < sheetRows) return idx;
  }

  return 0;
}
