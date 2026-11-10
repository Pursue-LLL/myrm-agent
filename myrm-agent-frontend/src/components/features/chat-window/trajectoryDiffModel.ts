/**
 * [INPUT]
 * @/services/chat::SessionTrajectoryResponse (POS: a session's tool-call trajectory, turn by turn)
 *
 * [OUTPUT]
 * findDivergence: where two sessions first stop doing the same thing
 * turnStartIndexes: where each turn begins among all steps
 *
 * [POS]
 * Pure comparison rules of the trajectory diff modal.
 */

import { isEqual } from 'lodash-es';

import type { SessionTrajectoryResponse, TrajectoryStep, TurnTrajectory } from '@/services/chat';

const allSteps = (trajectory: SessionTrajectoryResponse): TrajectoryStep[] =>
  trajectory.turns.flatMap((turn) => turn.steps);

/**
 * Position, counted over the steps of all turns, where two sessions first stop doing the same thing: another tool,
 * other arguments (key order does not matter), or one session ending while the other goes on. Null when they ran alike.
 */
export function findDivergence(a: SessionTrajectoryResponse, b: SessionTrajectoryResponse): number | null {
  const stepsA = allSteps(a);
  const stepsB = allSteps(b);
  const shared = Math.min(stepsA.length, stepsB.length);

  for (let i = 0; i < shared; i++) {
    if (stepsA[i].tool_name !== stepsB[i].tool_name || !isEqual(stepsA[i].tool_args, stepsB[i].tool_args)) {
      return i;
    }
  }
  return stepsA.length === stepsB.length ? null : shared;
}

/** Position of each turn's first step among the steps of all turns, to place a divergence inside its turn. */
export function turnStartIndexes(turns: TurnTrajectory[]): number[] {
  let start = 0;
  return turns.map((turn) => {
    const first = start;
    start += turn.steps.length;
    return first;
  });
}
