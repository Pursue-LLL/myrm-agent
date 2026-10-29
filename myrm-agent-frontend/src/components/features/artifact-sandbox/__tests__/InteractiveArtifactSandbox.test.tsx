import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InteractiveArtifactSandbox } from '../InteractiveArtifactSandbox';
import { useArtifactSandboxStore } from '../useArtifactSandboxStore';

describe('InteractiveArtifactSandbox', () => {
  beforeEach(() => {
    useArtifactSandboxStore.getState().resetAll();
  });

  it('正常渲染沙盒控制栏、视口切换器与 iframe 容器', () => {
    render(<InteractiveArtifactSandbox />);
    expect(
      screen.getByTestId('interactive-artifact-sandbox')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('viewport-desktop-btn')
    ).toBeInTheDocument();
    expect(screen.getByTestId('viewport-tablet-btn')).toBeInTheDocument();
    expect(screen.getByTestId('viewport-mobile-btn')).toBeInTheDocument();
    expect(
      screen.getByTestId('sandbox-runtime-iframe')
    ).toBeInTheDocument();
  });

  it('支持切换桌面、平板与移动端视口宽度', () => {
    render(<InteractiveArtifactSandbox />);
    const iframe = screen.getByTestId('sandbox-runtime-iframe');
    expect(iframe.className).toContain('w-full');

    fireEvent.click(screen.getByTestId('viewport-tablet-btn'));
    expect(iframe.className).toContain('w-[768px]');

    fireEvent.click(screen.getByTestId('viewport-mobile-btn'));
    expect(iframe.className).toContain('w-[375px]');

    fireEvent.click(screen.getByTestId('viewport-desktop-btn'));
    expect(iframe.className).toContain('w-full');
  });

  it('点击重新载入按钮触发刷新与回调', () => {
    const handleReload = vi.fn();
    render(<InteractiveArtifactSandbox onReload={handleReload} />);

    const reloadBtn = screen.getByTestId('sandbox-reload-btn');
    fireEvent.click(reloadBtn);
    expect(handleReload).toHaveBeenCalledTimes(1);
  });

  it('点击全屏切换按钮更新 store 并触发回调', () => {
    const handleFullscreen = vi.fn();
    render(
      <InteractiveArtifactSandbox onFullscreenChange={handleFullscreen} />
    );

    const fsBtn = screen.getByTestId('sandbox-fullscreen-btn');
    fireEvent.click(fsBtn);

    expect(handleFullscreen).toHaveBeenCalledWith(true);
    expect(useArtifactSandboxStore.getState().isFullscreen).toBe(true);

    fireEvent.click(fsBtn);
    expect(handleFullscreen).toHaveBeenCalledWith(false);
    expect(useArtifactSandboxStore.getState().isFullscreen).toBe(false);
  });
});
