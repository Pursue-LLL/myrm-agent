import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLocalFirstStore } from '../useLocalFirstStore';
import { WebGPUMetaArtifactViewer } from '../WebGPUMetaArtifactViewer';

describe('WebGPUMetaArtifactViewer', () => {
  beforeEach(() => {
    useLocalFirstStore.getState().reset();
  });

  it('renders viewer title, 3D acceleration badge, and default viewport accurately', () => {
    render(<WebGPUMetaArtifactViewer />);

    expect(screen.getByTestId('webgpu-meta-artifact-viewer')).toBeDefined();
    expect(screen.getByText('WebGPU 模块化工件画布')).toBeDefined();
    expect(screen.getByText('WebGPU 3D 加速')).toBeDefined();
    expect(screen.getByText('WebGPU 3D 渲染管线已挂载')).toBeDefined();
    expect(screen.getByText('节点数: 12')).toBeDefined();
    expect(screen.getByText('60 FPS')).toBeDefined();
  });

  it('toggles render mode between WebGPU 3D and 2D Canvas fallback', () => {
    render(<WebGPUMetaArtifactViewer />);

    const toggleBtn = screen.getByLabelText('切换渲染引擎模式');
    fireEvent.click(toggleBtn);

    expect(screen.getByText('2D Canvas 降级')).toBeDefined();
    expect(
      screen.getByText('2D Canvas 平滑降级视口已挂载'),
    ).toBeDefined();

    fireEvent.click(toggleBtn);
    expect(screen.getByText('WebGPU 3D 加速')).toBeDefined();
  });

  it('handles scene reset button and invokes onSceneReload callback', () => {
    const onReload = vi.fn();
    render(<WebGPUMetaArtifactViewer onSceneReload={onReload} />);

    const resetBtn = screen.getByLabelText('重置画布场景');
    fireEvent.click(resetBtn);

    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it('navigates between viewport, nodes, and stats tabs', () => {
    render(<WebGPUMetaArtifactViewer />);

    // 切换到节点树
    fireEvent.click(screen.getByText('场景节点树'));
    expect(screen.getByText('Node_MeshGroup_01')).toBeDefined();
    expect(screen.getByText('顶点数: 240')).toBeDefined();

    // 切换到硬件指标
    fireEvent.click(screen.getByText('硬件指标'));
    expect(screen.getByText('着色器后端')).toBeDefined();
    expect(screen.getByText('WGSL / SPIR-V')).toBeDefined();
    expect(screen.getByText('GPU Accelerated')).toBeDefined();

    // 切换回视口画布
    fireEvent.click(screen.getByText('视口画布'));
    expect(screen.getByText('WebGPU 3D 渲染管线已挂载')).toBeDefined();
  });
});
