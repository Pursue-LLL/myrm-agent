import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useQuietMomentUpdateStore } from '../useQuietMomentUpdateStore';
import type { UpdateAvailabilitySnapshot } from '../quietMomentUpdateTypes';

describe('useQuietMomentUpdateStore', () => {
  beforeEach(() => {
    useQuietMomentUpdateStore.setState({
      generation: 1,
      snapshot: null,
      isOfferVisible: false,
      activeTipId: null,
      lastOfferedAt: undefined,
      dismissedVersions: [],
      isDismissModalOpen: false,
      lastTypedAt: 0,
      typingGraceMs: 5000,
      isWindowFocused: true,
      isDocumentVisible: true,
      hasActiveStreamingOrTask: false,
      hasBlockingSurface: false,
      connectionMode: 'local',
      isInstallingBusy: false,
    });
  });

  it('should initialize with default states', () => {
    const state = useQuietMomentUpdateStore.getState();
    expect(state.generation).toBe(1);
    expect(state.isOfferVisible).toBe(false);
    expect(state.connectionMode).toBe('local');
    expect(state.isWindowFocused).toBe(true);
  });

  it('should track typing and focus changes', () => {
    const store = useQuietMomentUpdateStore.getState();
    store.noteTyping(50_000);
    expect(useQuietMomentUpdateStore.getState().lastTypedAt).toBe(50_000);

    store.setWindowFocus(false);
    expect(useQuietMomentUpdateStore.getState().isWindowFocused).toBe(false);

    store.setDocumentVisibility(false);
    expect(useQuietMomentUpdateStore.getState().isDocumentVisible).toBe(false);
  });

  it('should increment generation and clear snapshot when connection mode changes', () => {
    const dummySnapshot: UpdateAvailabilitySnapshot = {
      version: '1.5.0',
      readAt: 10_000,
    };
    useQuietMomentUpdateStore.setState({
      snapshot: dummySnapshot,
      isOfferVisible: true,
      generation: 1,
      connectionMode: 'local',
    });

    useQuietMomentUpdateStore.getState().setConnectionMode('cloud');
    const state = useQuietMomentUpdateStore.getState();
    expect(state.generation).toBe(2);
    expect(state.snapshot).toBeNull();
    expect(state.isOfferVisible).toBe(false);
    expect(state.connectionMode).toBe('cloud');
  });

  it('should trigger quiet moment check and display offer when eligible', () => {
    const dummySnapshot: UpdateAvailabilitySnapshot = {
      version: '2.4.0',
      readAt: 10_000,
    };
    useQuietMomentUpdateStore.getState().setSnapshot(dummySnapshot);

    const now = 20_000;
    const result = useQuietMomentUpdateStore.getState().checkQuietMoment(now);
    expect(result).toBe(true);

    const state = useQuietMomentUpdateStore.getState();
    expect(state.isOfferVisible).toBe(true);
    expect(state.activeTipId).toBe('update-offer:2.4.0');
    expect(state.lastOfferedAt).toBe(now);
  });

  it('should handle version dismissal and snoozing', () => {
    const dummySnapshot: UpdateAvailabilitySnapshot = {
      version: '3.0.0',
      readAt: 10_000,
    };
    useQuietMomentUpdateStore.setState({
      snapshot: dummySnapshot,
      isOfferVisible: true,
      isDismissModalOpen: true,
    });

    useQuietMomentUpdateStore.getState().dismissVersion('3.0.0', 4, 10_000);
    const state = useQuietMomentUpdateStore.getState();
    expect(state.isOfferVisible).toBe(false);
    expect(state.isDismissModalOpen).toBe(false);
    expect(state.dismissedVersions.length).toBe(1);
    expect(state.dismissedVersions[0].version).toBe('3.0.0');
    expect(state.dismissedVersions[0].remindAfter).toBe(10_000 + 4 * 3_600_000);

    // Restore version
    useQuietMomentUpdateStore.getState().restoreVersion('3.0.0');
    expect(useQuietMomentUpdateStore.getState().dismissedVersions.length).toBe(0);
  });

  it('should execute action only when context is verified and valid', async () => {
    const onProceed = vi.fn();
    useQuietMomentUpdateStore.setState({
      generation: 1,
      isOfferVisible: true,
    });

    const success = await useQuietMomentUpdateStore.getState().executeAction(onProceed);
    expect(success).toBe(true);
    expect(onProceed).toHaveBeenCalledTimes(1);
    expect(useQuietMomentUpdateStore.getState().isOfferVisible).toBe(false);
  });

  it('should abort action if generation or task state becomes invalid', async () => {
    const onProceed = vi.fn();
    useQuietMomentUpdateStore.setState({
      generation: 1,
      isInstallingBusy: true,
      isOfferVisible: true,
    });

    const success = await useQuietMomentUpdateStore.getState().executeAction(onProceed);
    expect(success).toBe(false);
    expect(onProceed).not.toHaveBeenCalled();
    expect(useQuietMomentUpdateStore.getState().isOfferVisible).toBe(false);
  });
});
