import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CrossArtboardThemeLockBar } from '../CrossArtboardThemeLockBar';
import { InteractivePrototypePlayerModal } from '../InteractivePrototypePlayerModal';
import { useMultiArtboardStore } from '../useMultiArtboardStore';

describe('CrossArtboardThemeLockBar and InteractivePrototypePlayerModal', () => {
  beforeEach(() => {
    useMultiArtboardStore.getState().stopPlayback();
    useMultiArtboardStore.getState().resetViewport();
  });

  it('renders theme lock bar controls and triggers preset selection', () => {
    render(<CrossArtboardThemeLockBar />);

    expect(screen.getByText('风格锁激活')).toBeInTheDocument();
    expect(screen.getByText('全景平铺整理')).toBeInTheDocument();
    expect(screen.getByText('流转连线')).toBeInTheDocument();
    expect(screen.getByText('播放演示')).toBeInTheDocument();

    // 切换预设
    const select = screen.getByLabelText('选择全局设计风格预设');
    fireEvent.change(select, { target: { value: 'Cyber Emerald' } });

    expect(useMultiArtboardStore.getState().themeLock.presetName).toBe('Cyber Emerald');
    expect(useMultiArtboardStore.getState().themeLock.primaryColor).toBe('#10b981');
  });

  it('toggles theme lock active status and flow links', () => {
    render(<CrossArtboardThemeLockBar />);

    const lockBtn = screen.getByTitle('视觉风格已锁定：多画板继承统一规范');
    fireEvent.click(lockBtn);
    expect(useMultiArtboardStore.getState().themeLock.isLocked).toBe(false);

    const linksBtn = screen.getByTitle('切换是否显示画板间交互流转连线');
    fireEvent.click(linksBtn);
    expect(useMultiArtboardStore.getState().showFlowLinks).toBe(false);
  });

  it('launches prototype player modal on play click and supports zero-token page transitions', () => {
    render(
      <>
        <CrossArtboardThemeLockBar />
        <InteractivePrototypePlayerModal />
      </>
    );

    // 点击播放演示
    const playBtn = screen.getByText('播放演示');
    fireEvent.click(playBtn);

    expect(useMultiArtboardStore.getState().playbackState.isPlaying).toBe(true);
    expect(screen.getByRole('dialog', { name: '免 Token 交互原型播放器' })).toBeInTheDocument();
    expect(screen.getByText('01 · 工作台首页')).toBeInTheDocument();

    // 在手机外壳中点击带有 targetArtboardId 的按钮
    const scheduleBtn = screen.getByText('查看今日日程 ➔');
    fireEvent.click(scheduleBtn);

    // 状态流转到日程排期表
    expect(useMultiArtboardStore.getState().playbackState.currentArtboardId).toBe('artboard-schedule');
    expect(screen.getByText('02 · 日程排期表')).toBeInTheDocument();

    // 点击返回上一步
    const backBtn = screen.getByText('返回');
    fireEvent.click(backBtn);

    expect(useMultiArtboardStore.getState().playbackState.currentArtboardId).toBe('artboard-home');
    expect(screen.getByText('01 · 工作台首页')).toBeInTheDocument();

    // 点击退出演示
    const exitBtn = screen.getByText('退出演示');
    fireEvent.click(exitBtn);

    expect(useMultiArtboardStore.getState().playbackState.isPlaying).toBe(false);
  });

  it('switches device frame in playback mode', () => {
    useMultiArtboardStore.getState().startPlayback('artboard-home');
    render(<InteractivePrototypePlayerModal />);

    const ipadBtn = screen.getByTitle('切换为 iPad 演示外壳');
    fireEvent.click(ipadBtn);

    expect(useMultiArtboardStore.getState().playbackState.deviceFrame).toBe('ipad');
  });
});
