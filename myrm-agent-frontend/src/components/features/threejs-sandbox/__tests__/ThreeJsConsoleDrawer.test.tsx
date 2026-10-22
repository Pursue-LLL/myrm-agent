import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThreeJsConsoleDrawer } from '../ThreeJsConsoleDrawer';
import { useThreeJsSandboxStore } from '../useThreeJsSandboxStore';
import { WebGLLogEntry } from '../threeJsTypes';

const mockLogs: WebGLLogEntry[] = [
  {
    id: 'log-1',
    level: 'error',
    source: 'shader',
    message: 'Shader compile failed: syntax error near line 42',
    timestamp: '15:00:01',
    shaderInfo: {
      type: 'fragment',
      infoLog: 'Syntax error at line 42',
    },
  },
  {
    id: 'log-2',
    level: 'warn',
    source: 'texture',
    message: 'Texture dimensions are not power of two',
    timestamp: '15:00:02',
  },
  {
    id: 'log-3',
    level: 'info',
    source: 'runtime',
    message: 'WebGL 2.0 Context Initialized',
    timestamp: '15:00:00',
  },
];

describe('ThreeJsConsoleDrawer 组件单测', () => {
  beforeEach(() => {
    useThreeJsSandboxStore.setState({
      sceneId: 'test-scene-car',
      isConsoleOpen: true,
      logs: mockLogs,
      metrics: {
        fps: 60,
        drawCalls: 10,
        triangles: 1000,
        geometries: 5,
        textures: 2,
      },
    });
  });

  it('当 isConsoleOpen 为 false 时不渲染任何抽屉元素', () => {
    useThreeJsSandboxStore.setState({ isConsoleOpen: false });
    const { container } = render(<ThreeJsConsoleDrawer />);

    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('threejs-console-drawer')).not.toBeInTheDocument();
  });

  it('当 isConsoleOpen 为 true 时完整呈现控制台顶栏与日志列表', () => {
    render(<ThreeJsConsoleDrawer />);

    expect(screen.getByTestId('threejs-console-drawer')).toBeInTheDocument();
    expect(screen.getByText('WebGL 运行时自检控制台')).toBeInTheDocument();
    expect(screen.getByText('3 条记录')).toBeInTheDocument();
    expect(screen.getByText(/Shader compile failed/)).toBeInTheDocument();
    expect(screen.getByText(/Texture dimensions are not power of two/)).toBeInTheDocument();
    expect(screen.getByText(/WebGL 2.0 Context Initialized/)).toBeInTheDocument();
  });

  it('点击「一键 Agent 自愈」能触发 onSelfHealingTriggered 回调并包含诊断 Prompt', () => {
    const handleSelfHealing = vi.fn();
    render(<ThreeJsConsoleDrawer onSelfHealingTriggered={handleSelfHealing} />);

    const repairBtn = screen.getByText('一键 Agent 自愈');
    fireEvent.click(repairBtn);

    expect(handleSelfHealing).toHaveBeenCalledTimes(1);
    const passedDossier = handleSelfHealing.mock.calls[0][0];
    expect(passedDossier.sceneId).toBe('test-scene-car');
    expect(passedDossier.errorMessage).toContain('Shader compile failed');
    expect(passedDossier.repairInstructionPrompt).toContain('【WebGL 3D 场景运行时错误自愈请求】');
  });

  it('点击清空按钮清空全部日志，并显示空状态提示', () => {
    render(<ThreeJsConsoleDrawer />);

    const clearBtn = screen.getByRole('button', { name: '清空日志' });
    fireEvent.click(clearBtn);

    expect(useThreeJsSandboxStore.getState().logs.length).toBe(0);
    expect(screen.getByText('暂无 WebGL 报错或警告，运行时状态正常')).toBeInTheDocument();
  });

  it('点击关闭按钮能关闭控制台抽屉', () => {
    render(<ThreeJsConsoleDrawer />);

    const closeBtn = screen.getByRole('button', { name: '关闭控制台' });
    fireEvent.click(closeBtn);

    expect(useThreeJsSandboxStore.getState().isConsoleOpen).toBe(false);
  });
});
