import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SkeuomorphicWorkbenchWidget } from '../SkeuomorphicWorkbenchWidget';
import { useSkeuomorphicAppStore } from '../useSkeuomorphicAppStore';

describe('SkeuomorphicWorkbenchWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSkeuomorphicAppStore.getState().resetStore();
  });

  it('默认状态应渲染完整面板与 iPod 皮肤', () => {
    render(<SkeuomorphicWorkbenchWidget />);

    expect(screen.getByTestId('skeuomorphic-workbench-widget')).toBeInTheDocument();
    expect(screen.getByTestId('classic-ipod-player')).toBeInTheDocument();
    expect(screen.getByText('JIT Skeuomorphic Visualizer')).toBeInTheDocument();
  });

  it('点击顶部 Polaroid 按钮能切换为拍立得相册皮肤', () => {
    render(<SkeuomorphicWorkbenchWidget />);

    const polaroidBtn = screen.getByRole('button', { name: /Polaroid/i });
    fireEvent.click(polaroidBtn);

    expect(screen.getByTestId('polaroid-album-deck')).toBeInTheDocument();
    expect(screen.queryByTestId('classic-ipod-player')).not.toBeInTheDocument();

    const ipodBtn = screen.getByRole('button', { name: /iPod/i });
    fireEvent.click(ipodBtn);

    expect(screen.getByTestId('classic-ipod-player')).toBeInTheDocument();
  });

  it('点击音效和触感控制按钮能切换 store 状态', () => {
    render(<SkeuomorphicWorkbenchWidget />);

    const soundBtn = screen.getByRole('button', { name: /切换声音/i });
    fireEvent.click(soundBtn);
    expect(useSkeuomorphicAppStore.getState().soundEnabled).toBe(false);

    const hapticBtn = screen.getByRole('button', { name: /切换触感/i });
    fireEvent.click(hapticBtn);
    expect(useSkeuomorphicAppStore.getState().hapticEnabled).toBe(false);
  });

  it('点击最小化按钮能折叠为精致悬浮胶囊栏，点击胶囊可再次展开', () => {
    render(<SkeuomorphicWorkbenchWidget />);

    const minBtn = screen.getByRole('button', { name: /最小化/i });
    fireEvent.click(minBtn);

    expect(screen.getByTestId('skeuomorphic-minimized-pill')).toBeInTheDocument();
    expect(screen.queryByTestId('skeuomorphic-workbench-widget')).not.toBeInTheDocument();

    const expandBtn = screen.getByRole('button', { name: /展开挂件/i });
    fireEvent.click(expandBtn);

    expect(screen.getByTestId('skeuomorphic-workbench-widget')).toBeInTheDocument();
  });
});
