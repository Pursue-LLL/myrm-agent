import { describe, expect, it } from 'vitest';

import { PetState } from '../PetStateMachine';
import {
  pickPetBubbleSpec,
  shouldShowPetStatusBubble,
} from '../petStatusBubbleSpec';

describe('petStatusBubbleSpec', () => {
  it('shows bubble only for active work states', () => {
    expect(shouldShowPetStatusBubble(PetState.IDLE)).toBe(false);
    expect(shouldShowPetStatusBubble(PetState.RUNNING)).toBe(true);
    expect(shouldShowPetStatusBubble(PetState.WAITING)).toBe(true);
  });

  it('returns wait tone for WAITING state', () => {
    const spec = pickPetBubbleSpec(PetState.WAITING, null);
    expect(spec).not.toBeNull();
    expect(spec?.tone).toBe('wait');
    expect(spec?.messageKey).toMatch(/^wait/);
  });

  it('avoids repeating the same message key when pool has alternatives', () => {
    const spec = pickPetBubbleSpec(PetState.RUNNING, 'run0');
    expect(spec?.messageKey).not.toBe('run0');
  });
});
