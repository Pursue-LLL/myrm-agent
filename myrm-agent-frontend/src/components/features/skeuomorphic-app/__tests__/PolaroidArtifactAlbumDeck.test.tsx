import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PolaroidArtifactAlbumDeck } from '../PolaroidArtifactAlbumDeck';
import { useSkeuomorphicAppStore } from '../useSkeuomorphicAppStore';

describe('PolaroidArtifactAlbumDeck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSkeuomorphicAppStore.getState().resetStore();
  });

  it('应正确渲染拍立得机身指示、白边相纸卡片与当前工件标题', () => {
    render(<PolaroidArtifactAlbumDeck />);

    expect(screen.getByTestId('polaroid-album-deck')).toBeInTheDocument();
    expect(screen.getByText(/Polaroid SnapDeck/)).toBeInTheDocument();
    expect(screen.getByText(/重构前端会话上下文数据获取模型/)).toBeInTheDocument();
    expect(screen.getByText(/CODE/)).toBeInTheDocument();
    expect(screen.getByText(/By Arch-Master-4o/)).toBeInTheDocument();
  });

  it('点击左/右翻页按钮能向前/向后切换拍立得工件相片', () => {
    render(<PolaroidArtifactAlbumDeck />);

    const nextBtn = screen.getByRole('button', { name: /下一张相片/i });
    fireEvent.click(nextBtn);

    expect(
      screen.getByText(/设计拟物化复古 iPod 风格任务旋转播放器/)
    ).toBeInTheDocument();
    expect(screen.getByText(/DESIGN/)).toBeInTheDocument();

    const prevBtn = screen.getByRole('button', { name: /上一张相片/i });
    fireEvent.click(prevBtn);

    expect(
      screen.getByText(/重构前端会话上下文数据获取模型/)
    ).toBeInTheDocument();
  });

  it('点击模拟快门冲印按钮不应抛出异常并触发交互', () => {
    render(<PolaroidArtifactAlbumDeck />);

    const snapBtn = screen.getByRole('button', { name: /拍摄并冲印/i });
    expect(() => fireEvent.click(snapBtn)).not.toThrow();

    const exportBtn = screen.getByRole('button', { name: /导出相片/i });
    expect(() => fireEvent.click(exportBtn)).not.toThrow();
  });
});
