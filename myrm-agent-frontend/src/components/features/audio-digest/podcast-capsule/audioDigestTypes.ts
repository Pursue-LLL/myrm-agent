/**
 * Artifact Audio Digest & Continuation Capsule Types
 * AI 工件自适应口语化音频播客简报与跨端连续性流转胶囊类型契约
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 字段完备语义化。
 */

export type PodcastSpeakerRole = 'host' | 'analyst';

export type DigestPlaybackState = 'idle' | 'playing' | 'paused' | 'ended';

export type PlaybackRate = 1.0 | 1.25 | 1.5 | 2.0;

export interface PodcastSegment {
  id: string;
  speaker: PodcastSpeakerRole;
  speakerName: string;
  text: string;
  startSecond: number;
  endSecond: number;
  sourceHeading: string;
  targetAnchorSelector?: string;
}

export interface ArtifactAudioDigest {
  id: string;
  artifactId: string;
  artifactTitle: string;
  totalDurationSeconds: number;
  audioStreamUrl: string;
  segments: PodcastSegment[];
  summaryHighlight: string;
  generatedAtTimestamp: number;
}

export interface ContinuationCapsule {
  capsuleId: string;
  artifactId: string;
  artifactTitle: string;
  playbackSecond: number;
  activeSegmentId: string;
  targetAnchorSelector: string;
  sourceDevice: string;
  createdAtTimestamp: number;
  continuationQrUrl: string;
}

export interface CapsuleResumeResult {
  capsuleId: string;
  artifactId: string;
  resumedAtTimestamp: number;
  targetAnchorSelector: string;
  status: 'resumed' | 'expired';
}
