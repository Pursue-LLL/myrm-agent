import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAudioDigestStore } from '../useAudioDigestStore';

describe('useAudioDigestStore', () => {
  beforeEach(() => {
    useAudioDigestStore.getState().resetToDefaults();
    vi.restoreAllMocks();
  });

  it('初始状态具备默认工件简报、空流转胶囊与初始播放进度', () => {
    const state = useAudioDigestStore.getState();
    expect(state.currentDigest.id).toBe('digest-art-09-perf-review');
    expect(state.playbackState).toBe('idle');
    expect(state.currentSecond).toBe(0);
    expect(state.playbackRate).toBe(1.0);
    expect(state.activeSegment?.id).toBe('seg-01');
    expect(state.activeCapsule).toBeNull();
    expect(state.isCapsuleModalOpen).toBe(false);
  });

  it('播放、暂停与状态切换正确跃迁', () => {
    useAudioDigestStore.getState().play();
    expect(useAudioDigestStore.getState().playbackState).toBe('playing');

    useAudioDigestStore.getState().pause();
    expect(useAudioDigestStore.getState().playbackState).toBe('paused');

    useAudioDigestStore.getState().togglePlayPause();
    expect(useAudioDigestStore.getState().playbackState).toBe('playing');

    useAudioDigestStore.getState().togglePlayPause();
    expect(useAudioDigestStore.getState().playbackState).toBe('paused');
  });

  it('seekToSecond 能够精确定位段落并派发 myrm:audio-digest-segment-change 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useAudioDigestStore.getState().seekToSecond(45);

    const state = useAudioDigestStore.getState();
    expect(state.currentSecond).toBe(45);
    expect(state.activeSegment?.id).toBe('seg-03');

    expect(dispatchSpy).toHaveBeenCalled();
    const event = dispatchSpy.mock.calls.find(
      (call) =>
        (call[0] as CustomEvent).type === 'myrm:audio-digest-segment-change'
    );
    expect(event).toBeDefined();
    if (event) {
      const customEvent = event[0] as CustomEvent;
      expect(customEvent.detail.segment.id).toBe('seg-03');
      expect(customEvent.detail.second).toBe(45);
    }
  });

  it('skipSeconds 能够快退与快进', () => {
    useAudioDigestStore.getState().seekToSecond(30);

    useAudioDigestStore.getState().skipSeconds(15);
    expect(useAudioDigestStore.getState().currentSecond).toBe(45);

    useAudioDigestStore.getState().skipSeconds(-20);
    expect(useAudioDigestStore.getState().currentSecond).toBe(25);
  });

  it('setPlaybackRate 能够更新倍速', () => {
    useAudioDigestStore.getState().setPlaybackRate(1.5);
    expect(useAudioDigestStore.getState().playbackRate).toBe(1.5);

    useAudioDigestStore.getState().setPlaybackRate(2.0);
    expect(useAudioDigestStore.getState().playbackRate).toBe(2.0);
  });

  it('生成连续性流转胶囊并打开弹窗', () => {
    useAudioDigestStore.getState().seekToSecond(20);
    useAudioDigestStore
      .getState()
      .generateContinuationCapsule('Apple Watch Series 10');

    const state = useAudioDigestStore.getState();
    expect(state.activeCapsule).toBeDefined();
    expect(state.activeCapsule?.sourceDevice).toBe('Apple Watch Series 10');
    expect(state.activeCapsule?.playbackSecond).toBe(20);
    expect(state.isCapsuleModalOpen).toBe(true);
  });

  it('大屏从流转胶囊接力恢复能够同步进度并派发 myrm:capsule-continuation-resumed 事件', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useAudioDigestStore.getState().seekToSecond(18);
    useAudioDigestStore.getState().generateContinuationCapsule('CarPlay');

    const capsule = useAudioDigestStore.getState().activeCapsule;
    expect(capsule).toBeDefined();

    if (capsule) {
      useAudioDigestStore.getState().resumeFromCapsule(capsule);

      const state = useAudioDigestStore.getState();
      expect(state.resumedAnchorTarget).toBe(capsule.targetAnchorSelector);
      expect(state.isCapsuleModalOpen).toBe(false);

      expect(dispatchSpy).toHaveBeenCalled();
      const resumeEvent = dispatchSpy.mock.calls.find(
        (call) =>
          (call[0] as CustomEvent).type === 'myrm:capsule-continuation-resumed'
      );
      expect(resumeEvent).toBeDefined();
    }
  });
});
