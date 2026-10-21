import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useStarMapStore } from '../useStarMapStore';
import { INITIAL_STAR_MAP_NODES } from '../starMapCatalogData';

describe('useStarMapStore', () => {
  beforeEach(() => {
    useStarMapStore.getState().resetState();
  });

  it('initializes with positioned nodes and default playback/filter state', () => {
    const state = useStarMapStore.getState();
    expect(state.nodes.length).toBe(INITIAL_STAR_MAP_NODES.length);
    expect(state.nodes[0].radialPosition).toBeDefined();
    expect(state.viewMode).toBe('map');
    expect(state.filter.scope).toBe('all');
    expect(state.filter.hideLabels).toBe(false);
    expect(state.playback.isPlaying).toBe(false);
    expect(state.playback.currentProgress).toBe(1.0);
  });

  it('updates filters and switches view mode', () => {
    const store = useStarMapStore.getState();

    store.setFilter({ scope: 'used', type: 'skill' });
    expect(useStarMapStore.getState().filter.scope).toBe('used');
    expect(useStarMapStore.getState().filter.type).toBe('skill');

    store.setViewMode('list');
    expect(useStarMapStore.getState().viewMode).toBe('list');

    store.setViewMode('map');
    expect(useStarMapStore.getState().viewMode).toBe('map');
  });

  it('manages selected node and detail sheet open/close', () => {
    const store = useStarMapStore.getState();
    const testId = INITIAL_STAR_MAP_NODES[0].id;

    store.openDetailSheet(testId);
    expect(useStarMapStore.getState().selectedNodeId).toBe(testId);
    expect(useStarMapStore.getState().isDetailSheetOpen).toBe(true);

    store.closeDetailSheet();
    expect(useStarMapStore.getState().isDetailSheetOpen).toBe(false);
  });

  it('controls playback progress, playback speed and toggle', () => {
    const store = useStarMapStore.getState();

    store.setPlaybackProgress(0.5);
    expect(useStarMapStore.getState().playback.currentProgress).toBe(0.5);
    expect(useStarMapStore.getState().playback.currentCutoffTimestamp).toBeDefined();

    store.setPlaybackSpeed(2);
    expect(useStarMapStore.getState().playback.playbackSpeed).toBe(2);

    store.togglePlayback();
    expect(useStarMapStore.getState().playback.isPlaying).toBe(true);

    store.togglePlayback();
    expect(useStarMapStore.getState().playback.isPlaying).toBe(false);
  });

  it('toggles hide labels privacy mode', () => {
    const store = useStarMapStore.getState();

    store.toggleHideLabels();
    expect(useStarMapStore.getState().filter.hideLabels).toBe(true);

    store.toggleHideLabels();
    expect(useStarMapStore.getState().filter.hideLabels).toBe(false);
  });

  it('dispatches custom event on star map export', async () => {
    const store = useStarMapStore.getState();
    const eventSpy = vi.fn();

    window.addEventListener('myrm:star-map-image-exported', eventSpy);

    const success = await store.exportStarMapImage();
    expect(success).toBe(true);
    expect(eventSpy).toHaveBeenCalledTimes(1);

    window.removeEventListener('myrm:star-map-image-exported', eventSpy);
  });
});
