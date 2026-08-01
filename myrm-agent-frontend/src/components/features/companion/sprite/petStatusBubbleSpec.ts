/**
 * Maps PetState → bubble visibility + i18n key suffix (companion.sprite.bubble.*).
 */

import { PetState } from './PetStateMachine';

export type PetBubbleTone = 'neutral' | 'wait' | 'error';

export interface PetBubbleSpec {
  messageKey: string;
  tone: PetBubbleTone;
}

const STATE_KEYS: Partial<Record<PetState, readonly string[]>> = {
  [PetState.RUNNING]: ['run0', 'run1', 'run2'],
  [PetState.REVIEWING]: ['review0', 'review1', 'review2'],
  [PetState.FAILED]: ['failed0', 'failed1'],
  [PetState.WAITING]: ['wait0', 'wait1', 'wait2'],
};

export function shouldShowPetStatusBubble(petState: PetState): boolean {
  return (
    petState === PetState.RUNNING
    || petState === PetState.REVIEWING
    || petState === PetState.FAILED
    || petState === PetState.WAITING
  );
}

export function pickPetBubbleSpec(petState: PetState, previousKey: string | null): PetBubbleSpec | null {
  if (!shouldShowPetStatusBubble(petState)) {
    return null;
  }

  const keys = STATE_KEYS[petState];
  if (!keys || keys.length === 0) {
    return null;
  }

  const pool = keys.length === 1 ? keys : keys.filter((k) => k !== previousKey);
  const picked = pool[Math.floor(Math.random() * pool.length)] ?? keys[0];

  const tone: PetBubbleTone =
    petState === PetState.WAITING ? 'wait'
      : petState === PetState.FAILED ? 'error'
        : 'neutral';

  return { messageKey: picked, tone };
}
