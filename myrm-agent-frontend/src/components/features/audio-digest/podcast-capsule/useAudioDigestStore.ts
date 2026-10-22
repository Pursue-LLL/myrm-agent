/**
 * Audio Digest & Continuation Capsule Store (Zustand)
 * AI 工件自适应口语化音频播客简报与跨端流转胶囊集中式状态总线
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 集中式事件广播与大屏原位锚定联动。
 */

import { create } from 'zustand';
import {
  ArtifactAudioDigest,
  ContinuationCapsule,
  DigestPlaybackState,
  PlaybackRate,
  PodcastSegment,
} from './audioDigestTypes';
import {
  createContinuationCapsule,
  findCurrentSegment,
  getDefaultMockAudioDigest,
} from './podcastSynthesizerEngine';

export interface AudioDigestState {
  currentDigest: ArtifactAudioDigest;
  playbackState: DigestPlaybackState;
  currentSecond: number;
  playbackRate: PlaybackRate;
  activeSegment: PodcastSegment | null;
  activeCapsule: ContinuationCapsule | null;
  isCapsuleModalOpen: boolean;
  resumedAnchorTarget: string | null;

  // Actions
  setDigest: (digest: ArtifactAudioDigest) => void;
  play: () => void;
  pause: () => void;
  togglePlayPause: () => void;
  seekToSecond: (second: number) => void;
  skipSeconds: (deltaSeconds: number) => void;
  setPlaybackRate: (rate: PlaybackRate) => void;
  generateContinuationCapsule: (sourceDevice?: string) => void;
  setCapsuleModalOpen: (open: boolean) => void;
  resumeFromCapsule: (capsule: ContinuationCapsule) => void;
  resetToDefaults: () => void;
}

const initialDigest = getDefaultMockAudioDigest();

export const useAudioDigestStore = create<AudioDigestState>(
  (set, get) => ({
    currentDigest: initialDigest,
    playbackState: 'idle',
    currentSecond: 0,
    playbackRate: 1.0,
    activeSegment: initialDigest.segments[0] || null,
    activeCapsule: null,
    isCapsuleModalOpen: false,
    resumedAnchorTarget: null,

    setDigest: (digest: ArtifactAudioDigest) => {
      set({
        currentDigest: digest,
        currentSecond: 0,
        playbackState: 'idle',
        activeSegment: digest.segments[0] || null,
        activeCapsule: null,
      });
    },

    play: () => {
      set({ playbackState: 'playing' });
    },

    pause: () => {
      set({ playbackState: 'paused' });
    },

    togglePlayPause: () => {
      const current = get().playbackState;
      if (current === 'playing') {
        set({ playbackState: 'paused' });
      } else {
        set({ playbackState: 'playing' });
      }
    },

    seekToSecond: (second: number) => {
      const digest = get().currentDigest;
      const targetSecond = Math.min(
        digest.totalDurationSeconds,
        Math.max(0, second)
      );

      const segment = findCurrentSegment(digest.segments, targetSecond);
      const isEnd = targetSecond >= digest.totalDurationSeconds;

      set({
        currentSecond: targetSecond,
        activeSegment: segment,
        playbackState: isEnd ? 'ended' : get().playbackState,
      });

      // 派发段落切换事件供宿主工件联动
      if (segment && typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:audio-digest-segment-change', {
            detail: { segment, second: targetSecond },
          })
        );
      }
    },

    skipSeconds: (deltaSeconds: number) => {
      const current = get().currentSecond;
      get().seekToSecond(current + deltaSeconds);
    },

    setPlaybackRate: (rate: PlaybackRate) => {
      set({ playbackRate: rate });
    },

    generateContinuationCapsule: (sourceDevice = 'Wearable Watch') => {
      const digest = get().currentDigest;
      const currentSecond = get().currentSecond;
      const capsule = createContinuationCapsule(
        digest,
        currentSecond,
        sourceDevice
      );

      set({
        activeCapsule: capsule,
        isCapsuleModalOpen: true,
      });
    },

    setCapsuleModalOpen: (open: boolean) => {
      set({ isCapsuleModalOpen: open });
    },

    resumeFromCapsule: (capsule: ContinuationCapsule) => {
      set({
        resumedAnchorTarget: capsule.targetAnchorSelector,
        isCapsuleModalOpen: false,
      });

      // 同步音频进度
      get().seekToSecond(capsule.playbackSecond);

      // 全局派发大屏接力流转事件，通知页面平滑滚动并高亮目标锚点
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:capsule-continuation-resumed', {
            detail: { capsule },
          })
        );
      }
    },

    resetToDefaults: () => {
      const defaultDigest = getDefaultMockAudioDigest();
      set({
        currentDigest: defaultDigest,
        playbackState: 'idle',
        currentSecond: 0,
        playbackRate: 1.0,
        activeSegment: defaultDigest.segments[0] || null,
        activeCapsule: null,
        isCapsuleModalOpen: false,
        resumedAnchorTarget: null,
      });
    },
  })
);
