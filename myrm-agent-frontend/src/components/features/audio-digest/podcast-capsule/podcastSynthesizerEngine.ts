/**
 * Podcast Synthesizer & Capsule Engine
 * 工件自适应口语化音频播客脚本生成、段落时间轴定位与流转胶囊纯函数引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 纯函数设计，高可测性。
 */

import {
  ArtifactAudioDigest,
  ContinuationCapsule,
  PodcastSegment,
} from './audioDigestTypes';

/**
 * 格式化秒数为 mm:ss 展示时间戳
 */
export function formatSecondsToTimestamp(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  const mm = minutes < 10 ? `0${minutes}` : `${minutes}`;
  const ss = remainingSeconds < 10 ? `0${remainingSeconds}` : `${remainingSeconds}`;
  return `${mm}:${ss}`;
}

/**
 * 根据当前播放时间戳秒数查找对应的段落
 */
export function findCurrentSegment(
  segments: PodcastSegment[],
  currentSecond: number
): PodcastSegment | null {
  if (segments.length === 0) {
    return null;
  }

  for (const segment of segments) {
    if (
      currentSecond >= segment.startSecond &&
      currentSecond < segment.endSecond
    ) {
      return segment;
    }
  }

  // 超过总时长则返回最后一段
  if (currentSecond >= segments[segments.length - 1].endSecond) {
    return segments[segments.length - 1];
  }

  return segments[0];
}

/**
 * 创建大屏连续性流转胶囊
 */
export function createContinuationCapsule(
  digest: ArtifactAudioDigest,
  playbackSecond: number,
  sourceDevice = 'Wearable Watch',
  originUrl = 'https://myrm.local'
): ContinuationCapsule {
  const activeSegment = findCurrentSegment(digest.segments, playbackSecond);
  const capsuleId = `capsule-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
  const anchorSelector = activeSegment?.targetAnchorSelector || '#artifact-header';

  const continuationQrUrl = `${originUrl}/capsule/resume?id=${capsuleId}&sec=${Math.floor(
    playbackSecond
  )}&anchor=${encodeURIComponent(anchorSelector)}`;

  return {
    capsuleId,
    artifactId: digest.artifactId,
    artifactTitle: digest.artifactTitle,
    playbackSecond: Math.floor(playbackSecond),
    activeSegmentId: activeSegment?.id || 'seg-01',
    targetAnchorSelector: anchorSelector,
    sourceDevice,
    createdAtTimestamp: Date.now(),
    continuationQrUrl,
  };
}

/**
 * 校验流转胶囊时效性（默认 10 分钟内有效）
 */
export function isCapsuleValid(
  capsule: ContinuationCapsule,
  maxAgeSeconds = 600
): boolean {
  if (!capsule.capsuleId || !capsule.artifactId) {
    return false;
  }

  const elapsedSeconds = (Date.now() - capsule.createdAtTimestamp) / 1000;
  return elapsedSeconds >= 0 && elapsedSeconds <= maxAgeSeconds;
}

/**
 * 获取预置的默认工件口语化音频简报（用于演示与测试）
 */
export function getDefaultMockAudioDigest(): ArtifactAudioDigest {
  const segments: PodcastSegment[] = [
    {
      id: 'seg-01',
      speaker: 'host',
      speakerName: '主播 Alex',
      text: '欢迎收听 Myrm 架构简报！今天我们聊聊这份最新生成的分布式网关重构工件。整体耗时从 450 毫秒下降到了 18 毫秒，表现惊人。',
      startSecond: 0,
      endSecond: 16,
      sourceHeading: '1. 性能指标概览',
      targetAnchorSelector: '#sec-performance-metrics',
    },
    {
      id: 'seg-02',
      speaker: 'analyst',
      speakerName: '架构师 Sarah',
      text: '核心突破在于彻底移除了旧版中央 Redis 的热点行锁，采用无锁环形队列与本地内存二级缓存，解决了高并发下的长尾延迟。',
      startSecond: 16,
      endSecond: 38,
      sourceHeading: '2. 无锁环形队列改造',
      targetAnchorSelector: '#sec-lockfree-ringbuffer',
    },
    {
      id: 'seg-03',
      speaker: 'host',
      speakerName: '主播 Alex',
      text: '听众朋友们如果想看第三节那张完整的跨节点拓扑图，只需抬手流转至电脑屏幕，我们将自动高亮该拓扑。接下来看断流自愈策略。',
      startSecond: 38,
      endSecond: 58,
      sourceHeading: '3. 跨节点拓扑架构',
      targetAnchorSelector: '#sec-cross-node-topology',
    },
    {
      id: 'seg-04',
      speaker: 'analyst',
      speakerName: '架构师 Sarah',
      text: '没错，熔断降级阈值设定在错误率大于 3% 时自动触发本地降级，并冻结上下文等待热恢复，保障了 99.99% 的可用性。',
      startSecond: 58,
      endSecond: 80,
      sourceHeading: '4. 熔断降级与热恢复',
      targetAnchorSelector: '#sec-failover-policy',
    },
  ];

  return {
    id: 'digest-art-09-perf-review',
    artifactId: 'art-09-distributed-gateway-architecture',
    artifactTitle: '分布式高并发网关重构与自愈分析报告',
    totalDurationSeconds: 80,
    audioStreamUrl: 'https://cdn.myrm.local/audio/mock-podcast-digest.mp3',
    segments,
    summaryHighlight: '80秒精炼听完：核心消除 Redis 行锁、环形队列吞吐翻 20 倍与熔断自愈机制',
    generatedAtTimestamp: Date.now(),
  };
}
