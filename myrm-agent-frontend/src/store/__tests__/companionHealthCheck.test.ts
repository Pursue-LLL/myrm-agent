import { beforeEach, describe, expect, it } from 'vitest';

import useCompanionStore from '@/store/useCompanionStore';

describe('openCompanionHealthCheck', () => {
  beforeEach(() => {
    useCompanionStore.setState({
      petPaletteOpen: false,
      doctorExpandPending: false,
    });
  });

  it('opens pet palette and marks doctor panel for expand', () => {
    useCompanionStore.getState().openCompanionHealthCheck();
    const state = useCompanionStore.getState();
    expect(state.petPaletteOpen).toBe(true);
    expect(state.doctorExpandPending).toBe(true);
  });

  it('clears doctor expand pending flag', () => {
    useCompanionStore.setState({ doctorExpandPending: true });
    useCompanionStore.getState().clearDoctorExpandPending();
    expect(useCompanionStore.getState().doctorExpandPending).toBe(false);
  });
});
