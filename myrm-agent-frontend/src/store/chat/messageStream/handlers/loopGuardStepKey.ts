/**
 * [INPUT]
 * - harness STATUS `data.loop_kind` (POS: loop pattern the guard fired on; `iteration_budget` for the round-budget nudges)
 * - locales progressSteps.loop_guard_warn* / loop_guard_break* (POS: 6-locale loop guard step titles and stop toast)
 *
 * [OUTPUT]
 * - isLoopGuardStep(): whether a STATUS step_key is a loop guard step
 * - loopGuardProgressStepKey(): progressSteps step_key a loop guard STATUS event is shown under
 * - LOOP_GUARD_BREAK_TOAST_KEY: i18n key of the toast that tells the user the agent was stopped
 *
 * [POS]
 * Wording SSOT for loop guard STATUS events: the harness names the loop kind, the UI words it in the user's language.
 */

export const LOOP_GUARD_BREAK_TOAST_KEY = 'progressSteps.loop_guard_break_toast';

/** Loop kinds in which the agent repeats itself without getting anywhere. */
const REPEATING_KINDS = new Set(['repetition', 'ping_pong', 'no_progress']);

export function isLoopGuardStep(stepKey: string): boolean {
  return stepKey === 'loop_guard_warn' || stepKey === 'loop_guard_break';
}

/** The kind of a warning picks its wording; a stop has one wording whatever the kind. */
export function loopGuardProgressStepKey(stepKey: string, loopKind: unknown): string {
  if (stepKey !== 'loop_guard_warn') {
    return stepKey;
  }
  if (loopKind === 'iteration_budget') {
    return 'loop_guard_warn_budget';
  }
  return typeof loopKind === 'string' && REPEATING_KINDS.has(loopKind) ? 'loop_guard_warn_repeat' : stepKey;
}
