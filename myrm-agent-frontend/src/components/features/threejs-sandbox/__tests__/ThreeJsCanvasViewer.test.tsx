import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ThreeJsCanvasViewer } from '../ThreeJsCanvasViewer';
import { useThreeJsSandboxStore } from '../useThreeJsSandboxStore';

describe('ThreeJsCanvasViewer 核心容器组件单测', () => {
  beforeEach(() => {
    useThreeJsSandboxStore.setState({
      sceneId: 'test-forest-zombie',
      sceneTitle: '林渊：最后一夜 3D 原型',
      sceneCode: 'console.log("3D Sandbox Loaded");',
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

  it('渲染主容器、工具栏、iframe 与性能指示板', () => {
    render(<ThreeJsCanvasViewer />);

    expect(screen.getByTestId('threejs-canvas-viewer')).toBeInTheDocument();
    expect(screen.getByText('林渊：最后一夜 3D 原型')).toBeInTheDocument();
    expect(screen.getByText('WebGL 2.0')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '复位相机' })).toBeInTheDocument();
    expect(screen.getByTestId('threejs-performance-panel')).toBeInTheDocument();

    const iframe = screen.getByTitle('林渊：最后一夜 3D 原型');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('sandbox', 'allow-scripts allow-pointer-lock allow-same-origin');
  });

  it('点击观察与试玩按钮切换相机模式和底部操作指南', () => {
    render(<ThreeJsCanvasViewer />);

    const playBtn = screen.getByText('试玩');
    fireEvent.click(playBtn);

    expect(useThreeJsSandboxStore.getState().cameraMode).toBe('pointer_lock');
    expect(screen.getByText(/已启用鼠标指针锁定与 WASD 键盘穿透/)).toBeInTheDocument();

    const orbitBtn = screen.getByText('观察');
    fireEvent.click(orbitBtn);

    expect(useThreeJsSandboxStore.getState().cameraMode).toBe('orbit');
    expect(screen.getByText(/按住鼠标左键旋转视角/)).toBeInTheDocument();
  });

  it('点击全屏与画中画按钮更新视口模式', () => {
    render(<ThreeJsCanvasViewer />);

    const fullscreenBtn = screen.getByRole('button', { name: '全屏' });
    fireEvent.click(fullscreenBtn);
    expect(useThreeJsSandboxStore.getState().viewportMode).toBe('fullscreen');

    const exitFullscreenBtn = screen.getByRole('button', { name: '全屏' });
    fireEvent.click(exitFullscreenBtn);
    expect(useThreeJsSandboxStore.getState().viewportMode).toBe('inline');

    const pipBtn = screen.getByRole('button', { name: '画中画' });
    fireEvent.click(pipBtn);
    expect(useThreeJsSandboxStore.getState().viewportMode).toBe('pip');
  });

  it('点击相机复位按钮触发 cameraResetCount 递增', () => {
    render(<ThreeJsCanvasViewer />);

    const resetBtn = screen.getByRole('button', { name: '复位相机' });
    fireEvent.click(resetBtn);

    expect(useThreeJsSandboxStore.getState().cameraResetCount).toBe(1);
  });

  it('响应 iframe postMessage 桥接事件更新性能与错误日志', () => {
    render(<ThreeJsCanvasViewer />);

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            source: 'threejs-sandbox',
            type: 'metrics',
            payload: { fps: 52, drawCalls: 28 },
          },
        })
      );
    });

    expect(useThreeJsSandboxStore.getState().metrics.fps).toBe(52);
    expect(useThreeJsSandboxStore.getState().metrics.drawCalls).toBe(28);

    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          data: {
            source: 'threejs-sandbox',
            type: 'log',
            payload: {
              level: 'error',
              source: 'runtime',
              message: 'GL_OUT_OF_MEMORY',
              timestamp: '16:00:00',
            },
          },
        })
      );
    });

    expect(useThreeJsSandboxStore.getState().logs.length).toBe(1);
    expect(useThreeJsSandboxStore.getState().logs[0].message).toBe('GL_OUT_OF_MEMORY');
  });
});
