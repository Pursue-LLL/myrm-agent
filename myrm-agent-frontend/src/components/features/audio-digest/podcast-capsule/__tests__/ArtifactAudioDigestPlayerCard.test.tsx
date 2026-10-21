import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ArtifactAudioDigestPlayerCard } from '../ArtifactAudioDigestPlayerCard';
import { useAudioDigestStore } from '../useAudioDigestStore';

describe('ArtifactAudioDigestPlayerCard', () => {
  beforeEach(() => {
    useAudioDigestStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('正确渲染播客标题、一句话亮点、时间戳与波形动画', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    expect(screen.getByTestId('audio-digest-player-card')).toBeInTheDocument();
    expect(
      screen.getByText('分布式高并发网关重构与自愈分析报告')
    ).toBeInTheDocument();
    expect(screen.getByText('播客简报')).toBeInTheDocument();
    expect(screen.getByTestId('current-time-text')).toHaveTextContent('00:00');
    expect(screen.getByTestId('total-duration-text')).toHaveTextContent('01:20');
    expect(screen.getByTestId('waveform-indicator')).toBeInTheDocument();
  });

  it('点击播放/暂停按钮能够切换播放状态', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    const playPauseBtn = screen.getByTestId('play-pause-toggle-btn');
    fireEvent.click(playPauseBtn);

    expect(useAudioDigestStore.getState().playbackState).toBe('playing');

    fireEvent.click(playPauseBtn);
    expect(useAudioDigestStore.getState().playbackState).toBe('paused');
  });

  it('点击倍速按钮能够更新倍速', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    const rate15Btn = screen.getByTestId('playback-rate-btn-1.5');
    fireEvent.click(rate15Btn);

    expect(useAudioDigestStore.getState().playbackRate).toBe(1.5);
  });

  it('点击快进 15 秒与快退 15 秒按钮能够推进进度', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    const skipForwardBtn = screen.getByTestId('skip-forward-15s-btn');
    fireEvent.click(skipForwardBtn);

    expect(useAudioDigestStore.getState().currentSecond).toBe(15);
    expect(screen.getByTestId('current-time-text')).toHaveTextContent('00:15');

    const skipBackBtn = screen.getByTestId('skip-back-15s-btn');
    fireEvent.click(skipBackBtn);

    expect(useAudioDigestStore.getState().currentSecond).toBe(0);
  });

  it('点击对白分段字幕能够快速跳转至对应章节', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    const seg2Btn = screen.getByTestId('transcript-segment-seg-02');
    fireEvent.click(seg2Btn);

    expect(useAudioDigestStore.getState().currentSecond).toBe(16);
    expect(useAudioDigestStore.getState().activeSegment?.id).toBe('seg-02');
  });

  it('点击流转大屏按钮能够呼出流转胶囊弹窗', () => {
    render(<ArtifactAudioDigestPlayerCard />);

    const capsuleBtn = screen.getByTestId('trigger-continuation-capsule-btn');
    fireEvent.click(capsuleBtn);

    expect(useAudioDigestStore.getState().isCapsuleModalOpen).toBe(true);
    expect(useAudioDigestStore.getState().activeCapsule).toBeDefined();
  });
});
