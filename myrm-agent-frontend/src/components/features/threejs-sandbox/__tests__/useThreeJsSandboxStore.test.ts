import { describe, it, expect, beforeEach } from 'vitest';
import { useThreeJsSandboxStore } from '../useThreeJsSandboxStore';

describe('useThreeJsSandboxStore 状态管理单测', () => {
  beforeEach(() => {
    useThreeJsSandboxStore.setState({
      sceneId: 'scene-default',
      sceneTitle: '3D 场景沙箱',
      sceneCode: '',
      viewportMode: 'inline',
      cameraMode: 'orbit',
      logs: [],
      isConsoleOpen: false,
      isStatsOpen: true,
      cameraResetCount: 0,
      metrics: {
        fps: 60,
        drawCalls: 1,
        triangles: 0,
        geometries: 0,
        textures: 0,
      },
    });
  });

  it('setScene 能正确更新场景代码、重置日志与性能指标', () => {
    useThreeJsSandboxStore.getState().addLog({
      level: 'warn',
      message: 'old warning',
      timestamp: '10:00:00',
    });

    useThreeJsSandboxStore.getState().setScene('car-3d-proto', '赛车原型', 'console.log("3D Car")');

    const state = useThreeJsSandboxStore.getState();
    expect(state.sceneId).toBe('car-3d-proto');
    expect(state.sceneTitle).toBe('赛车原型');
    expect(state.sceneCode).toBe('console.log("3D Car")');
    expect(state.logs.length).toBe(0);
    expect(state.metrics.fps).toBe(60);
  });

  it('updateMetrics 能局部更新渲染性能指标', () => {
    useThreeJsSandboxStore.getState().updateMetrics({
      fps: 48,
      drawCalls: 35,
      triangles: 12500,
    });

    const state = useThreeJsSandboxStore.getState();
    expect(state.metrics.fps).toBe(48);
    expect(state.metrics.drawCalls).toBe(35);
    expect(state.metrics.triangles).toBe(12500);
    expect(state.metrics.geometries).toBe(0);
  });

  it('addLog 能追加日志并限制最大 100 条记录', () => {
    for (let i = 0; i < 110; i++) {
      useThreeJsSandboxStore.getState().addLog({
        level: 'info',
        message: `log message ${i}`,
        timestamp: '10:00:00',
      });
    }

    const state = useThreeJsSandboxStore.getState();
    expect(state.logs.length).toBe(100);
    expect(state.logs[0].message).toBe('log message 109');
  });

  it('模式切换与相机复位计数正常流转', () => {
    const store = useThreeJsSandboxStore.getState();

    store.setViewportMode('fullscreen');
    expect(useThreeJsSandboxStore.getState().viewportMode).toBe('fullscreen');

    store.setCameraMode('pointer_lock');
    expect(useThreeJsSandboxStore.getState().cameraMode).toBe('pointer_lock');

    store.toggleConsole();
    expect(useThreeJsSandboxStore.getState().isConsoleOpen).toBe(true);

    store.toggleStats();
    expect(useThreeJsSandboxStore.getState().isStatsOpen).toBe(false);

    store.triggerCameraReset();
    expect(useThreeJsSandboxStore.getState().cameraResetCount).toBe(1);
  });
});
