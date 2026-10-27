/**
 * [INPUT]
 * @/lib/api::fetchWithTimeout (POS: REST with a deadline)
 * @/services/riskHeldToast::riskHeldErrorFromResponse (POS: the one notice for a note a risk rule holds)
 *
 * [OUTPUT]
 * - GoalActionOutcome: what became of a goal control: done, busy, held or failed.
 * - postGoalAction: sends one goal control and says what became of it, never throws.
 *
 * [POS]
 * The request behind every goal control (goal card, background-tasks panel, `/goal` command), so each of them tells a
 * goal that is still finishing its last step from a failure, and a held note from both, in the same way. The caller
 * words the outcome in its own toast; a held note has been explained here already.
 */

import type { GoalAction } from '@/components/features/chat-window/goals/goalStatusTypes';
import { fetchWithTimeout } from '@/lib/api';
import { riskHeldErrorFromResponse } from '@/services/riskHeldToast';

/**
 * - `done`: the server took the action.
 * - `busy`: the server refused to put the goal back to work because its previous turn is still finishing; the goal is
 *   as it was and the same action works once that turn has finished.
 * - `held`: a risk rule holds the note; its notice is shown and the goal is as it was.
 * - `failed`: anything else; the goal is as it was.
 */
export type GoalActionOutcome = 'done' | 'busy' | 'held' | 'failed';

const HTTP_CONFLICT = 409;

/** The actions that put the goal back to work, the only ones the server refuses with a conflict. */
const RESTARTING_ACTIONS: ReadonlySet<GoalAction> = new Set(['resume', 'unwait']);

export async function postGoalAction(chatId: string, action: GoalAction, note?: string): Promise<GoalActionOutcome> {
  try {
    const trimmedNote = note?.trim();
    const res = await fetchWithTimeout(`/goals/${chatId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trimmedNote ? { action, note: trimmedNote } : { action }),
    });
    if (res.ok) {
      return 'done';
    }
    if (res.status === HTTP_CONFLICT && RESTARTING_ACTIONS.has(action)) {
      return 'busy';
    }
    return (await riskHeldErrorFromResponse(res)) ? 'held' : 'failed';
  } catch (error) {
    console.error(`Network error: failed to ${action} goal`, error);
    return 'failed';
  }
}
