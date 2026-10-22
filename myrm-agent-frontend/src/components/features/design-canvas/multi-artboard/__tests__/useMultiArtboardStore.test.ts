import { describe, it, expect, beforeEach } from 'vitest';
import { useMultiArtboardStore } from '../useMultiArtboardStore';

describe('useMultiArtboardStore', () => {
  beforeEach(() => {
    // 重置状态
    useMultiArtboardStore.getState().stopPlayback();
    useMultiArtboardStore.getState().resetViewport();
    useMultiArtboardStore.getState().selectArtboard('artboard-home');
  });

  it('initializes with default artboards, flow links, and active theme lock', () => {
    const state = useMultiArtboardStore.getState();
    expect(state.artboards.length).toBe(4);
    expect(state.flowLinks.length).toBeGreaterThan(0);
    expect(state.themeLock.isLocked).toBe(true);
    expect(state.playbackState.isPlaying).toBe(false);
  });

  it('selects artboard and layer correctly', () => {
    const { selectArtboard, selectLayer } = useMultiArtboardStore.getState();

    selectArtboard('artboard-schedule');
    expect(useMultiArtboardStore.getState().selectedArtboardId).toBe('artboard-schedule');
    expect(useMultiArtboardStore.getState().selectedLayerId).toBeNull();

    selectLayer('artboard-schedule', 'btn-back-home-from-schedule');
    expect(useMultiArtboardStore.getState().selectedArtboardId).toBe('artboard-schedule');
    expect(useMultiArtboardStore.getState().selectedLayerId).toBe('btn-back-home-from-schedule');
  });

  it('updates artboard position when dragged', () => {
    const { updateArtboardPosition } = useMultiArtboardStore.getState();
    updateArtboardPosition('artboard-home', 150, 200);

    const updated = useMultiArtboardStore.getState().artboards.find((a) => a.id === 'artboard-home');
    expect(updated?.x).toBe(150);
    expect(updated?.y).toBe(200);
  });

  it('arranges artboards in a grid layout', () => {
    const { arrangeArtboardsGrid } = useMultiArtboardStore.getState();
    arrangeArtboardsGrid(2);

    const artboards = useMultiArtboardStore.getState().artboards;
    // 验证前两个和第三个的坐标符合两列排布
    expect(artboards[0].x).toBe(60);
    expect(artboards[1].x).toBeGreaterThan(artboards[0].x);
    expect(artboards[2].y).toBeGreaterThan(artboards[0].y);
  });

  it('toggles theme lock and updates theme properties across artboards', () => {
    const { updateThemeLock, toggleThemeLock } = useMultiArtboardStore.getState();

    updateThemeLock({ primaryColor: '#22c55e', borderRadius: 28 });
    const state = useMultiArtboardStore.getState();
    expect(state.themeLock.primaryColor).toBe('#22c55e');

    const homeArtboard = state.artboards.find((a) => a.id === 'artboard-home');
    const buttonLayer = homeArtboard?.layers.find((l) => l.type === 'button');
    expect(buttonLayer?.backgroundColor).toBe('#22c55e');
    expect(buttonLayer?.borderRadius).toBe(28);

    toggleThemeLock(false);
    expect(useMultiArtboardStore.getState().themeLock.isLocked).toBe(false);
  });

  it('manages prototype playback lifecycle, navigation history stack, and back transition', () => {
    const { startPlayback, navigatePlayback, goBackPlayback, stopPlayback } =
      useMultiArtboardStore.getState();

    // 启动演示
    startPlayback('artboard-home');
    let state = useMultiArtboardStore.getState();
    expect(state.playbackState.isPlaying).toBe(true);
    expect(state.playbackState.currentArtboardId).toBe('artboard-home');
    expect(state.playbackState.historyStack.length).toBe(0);

    // 点击跳转至日程页
    navigatePlayback('artboard-schedule', 'slide');
    state = useMultiArtboardStore.getState();
    expect(state.playbackState.currentArtboardId).toBe('artboard-schedule');
    expect(state.playbackState.historyStack).toEqual(['artboard-home']);

    // 再次跳转至详情/待办
    navigatePlayback('artboard-todo', 'slide');
    state = useMultiArtboardStore.getState();
    expect(state.playbackState.currentArtboardId).toBe('artboard-todo');
    expect(state.playbackState.historyStack).toEqual(['artboard-home', 'artboard-schedule']);

    // 返回上一步
    goBackPlayback();
    state = useMultiArtboardStore.getState();
    expect(state.playbackState.currentArtboardId).toBe('artboard-schedule');
    expect(state.playbackState.historyStack).toEqual(['artboard-home']);

    // 停止播放
    stopPlayback();
    expect(useMultiArtboardStore.getState().playbackState.isPlaying).toBe(false);
  });

  it('switches device frame and toggles hotspot hints', () => {
    const { setPlaybackDeviceFrame, togglePlaybackHotspotHints } =
      useMultiArtboardStore.getState();

    setPlaybackDeviceFrame('desktop');
    expect(useMultiArtboardStore.getState().playbackState.deviceFrame).toBe('desktop');

    togglePlaybackHotspotHints(false);
    expect(useMultiArtboardStore.getState().playbackState.showHotspotHints).toBe(false);
  });
});
