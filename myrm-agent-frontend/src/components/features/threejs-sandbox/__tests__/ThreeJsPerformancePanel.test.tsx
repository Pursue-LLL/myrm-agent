import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThreeJsPerformancePanel } from '../ThreeJsPerformancePanel';
import { useThreeJsSandboxStore } from '../useThreeJsSandboxStore';

describe('ThreeJsPerformancePanel 组件单测', () => {
  beforeEach(() => {
    useThreeJsSandboxStore.setState({
      isStatsOpen: true,
      metrics: {
        fps: 60,
        drawCalls: 12,
        triangles: 5400,
        geometries: 8,
        textures: 3,
      },
    });
  });

  it('当 isStatsOpen 为 false 时不渲染任何指标', () => {
    useThreeJsSandboxStore.setState({ isStatsOpen: false });
    const { container } = render(<ThreeJsPerformancePanel />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('threejs-performance-panel')).not.toBeInTheDocument();
  });

  it('当 isStatsOpen 为 true 时完整渲染各项性能数值', () => {
    render(<ThreeJsPerformancePanel />);

    expect(screen.getByTestId('threejs-performance-panel')).toBeInTheDocument();
    expect(screen.getByText('渲染引擎状态')).toBeInTheDocument();
    expect(screen.getByText('帧率 (FPS)')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('Draw Calls')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('5,400')).toBeInTheDocument();
    expect(screen.getByText('纹理: 3')).toBeInTheDocument();
    expect(screen.getByText('几何体: 8')).toBeInTheDocument();
  });

  it('低帧率时呈现警示颜色', () => {
    useThreeJsSandboxStore.setState({
      metrics: {
        fps: 22,
        drawCalls: 80,
        triangles: 120000,
        geometries: 50,
        textures: 10,
      },
    });

    render(<ThreeJsPerformancePanel />);
    const fpsElement = screen.getByText('22');
    expect(fpsElement).toHaveClass('text-rose-400');
  });
});
