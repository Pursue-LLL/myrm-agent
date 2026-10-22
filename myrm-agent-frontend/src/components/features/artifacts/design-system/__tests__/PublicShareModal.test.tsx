import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { PublicShareModal } from '../PublicShareModal';
import { useVisualArtifactStudioStore } from '../useVisualArtifactStudioStore';

describe('PublicShareModal', () => {
  beforeEach(() => {
    act(() => {
      useVisualArtifactStudioStore.getState().resetStudioState();
    });
  });

  it('当 isShareModalOpen 为 false 时不渲染任何 DOM', () => {
    const { container } = render(<PublicShareModal />);
    expect(container.firstChild).toBeNull();
  });

  it('打开弹窗后渲染配置项，点击生成按钮能够创建公网分享链接', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().openShareModal();
    });

    render(<PublicShareModal />);

    expect(
      screen.getByRole('dialog', { name: '零配置一键公网发布弹窗' })
    ).toBeInTheDocument();
    expect(screen.getByText('零配置一键公网安全发布')).toBeInTheDocument();

    const generateBtn = screen.getByRole('button', {
      name: '生成新的公网分享链接',
    });
    act(() => {
      fireEvent.click(generateBtn);
    });

    expect(screen.getByText(/https:\/\/share\.myrm\.io\/s\//)).toBeInTheDocument();
    expect(screen.getByText('已生成的分享短链 (1)')).toBeInTheDocument();
  });

  it('能够撤销已生成的公网分享链接', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().openShareModal();
      useVisualArtifactStudioStore
        .getState()
        .generatePublicShare('art_landing_demo_01', 24);
    });

    render(<PublicShareModal />);

    expect(screen.queryByText('已撤销')).toBeNull();

    const revokeBtn = screen.getByRole('button', { name: '撤销此短链' });
    act(() => {
      fireEvent.click(revokeBtn);
    });

    expect(screen.getByText('已撤销')).toBeInTheDocument();
  });

  it('点击关闭按钮关闭弹窗', () => {
    act(() => {
      useVisualArtifactStudioStore.getState().openShareModal();
    });

    render(<PublicShareModal />);

    const closeBtn = screen.getByRole('button', { name: '关闭公网发布弹窗' });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useVisualArtifactStudioStore.getState().isShareModalOpen).toBe(false);
  });
});
