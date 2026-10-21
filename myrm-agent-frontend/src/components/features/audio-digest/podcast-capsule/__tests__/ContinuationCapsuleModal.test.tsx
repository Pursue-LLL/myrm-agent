import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ContinuationCapsuleModal } from '../ContinuationCapsuleModal';
import { useAudioDigestStore } from '../useAudioDigestStore';

describe('ContinuationCapsuleModal', () => {
  beforeEach(() => {
    useAudioDigestStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('未打开时返回 null', () => {
    const { container } = render(<ContinuationCapsuleModal />);
    expect(container.firstChild).toBeNull();
  });

  it('打开时正确渲染流转胶囊、二维码区域与收听进度', () => {
    useAudioDigestStore.getState().seekToSecond(38);
    useAudioDigestStore
      .getState()
      .generateContinuationCapsule('Apple Watch Series 10');

    render(<ContinuationCapsuleModal />);

    expect(
      screen.getByTestId('continuation-capsule-modal-content')
    ).toBeInTheDocument();
    expect(screen.getByTestId('capsule-qr-code-box')).toBeInTheDocument();
    expect(screen.getByText(/收听进度：00:38/)).toBeInTheDocument();
    expect(screen.getByText('#sec-cross-node-topology')).toBeInTheDocument();
    expect(
      screen.getByText(/流转来源：Apple Watch Series 10/)
    ).toBeInTheDocument();
  });

  it('点击复制短链按钮能够写入剪贴板', () => {
    useAudioDigestStore.getState().generateContinuationCapsule();

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<ContinuationCapsuleModal />);

    const copyBtn = screen.getByTestId('copy-capsule-url-btn');
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalled();
  });

  it('点击在大屏定位到当前讨论章节能够调用 resumeFromCapsule', () => {
    useAudioDigestStore.getState().seekToSecond(58);
    useAudioDigestStore.getState().generateContinuationCapsule('Mobile Phone');

    render(<ContinuationCapsuleModal />);

    const resumeBtn = screen.getByTestId('resume-on-this-screen-btn');
    fireEvent.click(resumeBtn);

    expect(useAudioDigestStore.getState().isCapsuleModalOpen).toBe(false);
    expect(useAudioDigestStore.getState().resumedAnchorTarget).toBe(
      '#sec-failover-policy'
    );
  });

  it('点击关闭按钮或按 Escape 键能够关闭弹窗', () => {
    useAudioDigestStore.getState().generateContinuationCapsule();
    render(<ContinuationCapsuleModal />);

    const closeBtn = screen.getByTestId('close-capsule-modal-btn');
    fireEvent.click(closeBtn);

    expect(useAudioDigestStore.getState().isCapsuleModalOpen).toBe(false);
  });
});
