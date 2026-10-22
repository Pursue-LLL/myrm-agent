import { describe, it, expect, beforeEach } from 'vitest';
import { usePinnedDashboardStore } from '../usePinnedDashboardStore';

describe('usePinnedDashboardStore', () => {
  beforeEach(() => {
    usePinnedDashboardStore.getState().clearAllPins();
    usePinnedDashboardStore.getState().setDrawerOpen(false);
  });

  it('initializes with default state', () => {
    const state = usePinnedDashboardStore.getState();
    expect(state.pinnedWidgets).toEqual([]);
    expect(state.isDrawerOpen).toBe(false);
    expect(state.activeExportWidget).toBeNull();
  });

  it('pins a new widget with auto timestamp and avoids duplicates', () => {
    const store = usePinnedDashboardStore.getState();
    store.pinWidget({
      id: 'pin_1',
      artifactId: 'art_101',
      title: 'Counter Component',
      type: 'react',
      content: 'export default function App() { return <div>Count: 0</div> }',
      networkPolicy: 'none',
    });

    const stateAfterPin = usePinnedDashboardStore.getState();
    expect(stateAfterPin.pinnedWidgets.length).toBe(1);
    expect(stateAfterPin.pinnedWidgets[0].artifactId).toBe('art_101');
    expect(stateAfterPin.pinnedWidgets[0].networkPolicy).toBe('none');
    expect(stateAfterPin.pinnedWidgets[0].pinnedAt).toBeGreaterThan(0);

    // Attempt duplicate pin
    store.pinWidget({
      id: 'pin_dup',
      artifactId: 'art_101',
      title: 'Counter Duplicate',
      type: 'react',
      content: 'dup',
      networkPolicy: 'full',
    });
    expect(usePinnedDashboardStore.getState().pinnedWidgets.length).toBe(1);
  });

  it('unpins widget and resets activeExportWidget if it matches', () => {
    const store = usePinnedDashboardStore.getState();
    store.pinWidget({
      id: 'pin_1',
      artifactId: 'art_101',
      title: 'Counter Component',
      type: 'react',
      content: 'test',
      networkPolicy: 'none',
    });
    const pinned = usePinnedDashboardStore.getState().pinnedWidgets[0];
    store.setActiveExportWidget(pinned);
    expect(usePinnedDashboardStore.getState().activeExportWidget?.artifactId).toBe('art_101');

    store.unpinWidget('art_101');
    expect(usePinnedDashboardStore.getState().pinnedWidgets.length).toBe(0);
    expect(usePinnedDashboardStore.getState().activeExportWidget).toBeNull();
  });

  it('toggles pin state correctly and checks isPinned', () => {
    const store = usePinnedDashboardStore.getState();
    const widgetData = {
      id: 'pin_2',
      artifactId: 'art_202',
      title: 'Chart Widget',
      type: 'svg',
      content: '<svg></svg>',
      networkPolicy: 'restricted' as const,
    };

    expect(store.isPinned('art_202')).toBe(false);
    const pinResult = store.togglePin(widgetData);
    expect(pinResult).toBe(true);
    expect(usePinnedDashboardStore.getState().isPinned('art_202')).toBe(true);

    const unpinResult = store.togglePin(widgetData);
    expect(unpinResult).toBe(false);
    expect(usePinnedDashboardStore.getState().isPinned('art_202')).toBe(false);
  });

  it('updates network policy for a specific pinned widget', () => {
    const store = usePinnedDashboardStore.getState();
    store.pinWidget({
      id: 'pin_3',
      artifactId: 'art_303',
      title: 'Weather Widget',
      type: 'html',
      content: '<div>Sunny</div>',
      networkPolicy: 'none',
    });

    store.setNetworkPolicy('art_303', 'full');
    const updated = usePinnedDashboardStore.getState().pinnedWidgets.find((w) => w.artifactId === 'art_303');
    expect(updated?.networkPolicy).toBe('full');
  });

  it('controls drawer open and close states', () => {
    const store = usePinnedDashboardStore.getState();
    store.setDrawerOpen(true);
    expect(usePinnedDashboardStore.getState().isDrawerOpen).toBe(true);

    store.setDrawerOpen(false);
    expect(usePinnedDashboardStore.getState().isDrawerOpen).toBe(false);
  });

  it('clears all pinned widgets and export state', () => {
    const store = usePinnedDashboardStore.getState();
    store.pinWidget({
      id: 'pin_1',
      artifactId: 'art_1',
      title: 'W1',
      type: 'code',
      content: '1',
      networkPolicy: 'none',
    });
    store.pinWidget({
      id: 'pin_2',
      artifactId: 'art_2',
      title: 'W2',
      type: 'code',
      content: '2',
      networkPolicy: 'none',
    });

    expect(usePinnedDashboardStore.getState().pinnedWidgets.length).toBe(2);
    store.clearAllPins();
    expect(usePinnedDashboardStore.getState().pinnedWidgets).toEqual([]);
    expect(usePinnedDashboardStore.getState().activeExportWidget).toBeNull();
  });
});
