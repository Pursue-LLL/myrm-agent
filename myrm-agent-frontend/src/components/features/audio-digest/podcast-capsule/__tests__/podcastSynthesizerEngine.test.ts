import { describe, it, expect } from 'vitest';
import {
  formatSecondsToTimestamp,
  findCurrentSegment,
  createContinuationCapsule,
  isCapsuleValid,
  getDefaultMockAudioDigest,
} from '../podcastSynthesizerEngine';

describe('podcastSynthesizerEngine', () => {
  it('正确格式化秒数为 mm:ss 字符串', () => {
    expect(formatSecondsToTimestamp(0)).toBe('00:00');
    expect(formatSecondsToTimestamp(8)).toBe('00:08');
    expect(formatSecondsToTimestamp(65)).toBe('01:05');
    expect(formatSecondsToTimestamp(125)).toBe('02:05');
    expect(formatSecondsToTimestamp(-10)).toBe('00:00');
  });

  it('根据当前播放秒数准确定位对应的播客段落', () => {
    const digest = getDefaultMockAudioDigest();

    // 0 秒在 seg-01
    const seg1 = findCurrentSegment(digest.segments, 5);
    expect(seg1?.id).toBe('seg-01');

    // 25 秒在 seg-02 (16 - 38)
    const seg2 = findCurrentSegment(digest.segments, 25);
    expect(seg2?.id).toBe('seg-02');

    // 45 秒在 seg-03 (38 - 58)
    const seg3 = findCurrentSegment(digest.segments, 45);
    expect(seg3?.id).toBe('seg-03');

    // 超出总时长返回最后一段
    const segEnd = findCurrentSegment(digest.segments, 999);
    expect(segEnd?.id).toBe('seg-04');

    // 空列表返回 null
    expect(findCurrentSegment([], 10)).toBeNull();
  });

  it('创建连续性流转胶囊能够绑定当前收听秒数与工件锚点', () => {
    const digest = getDefaultMockAudioDigest();
    const capsule = createContinuationCapsule(
      digest,
      25,
      'Smart Watch',
      'https://myrm.example.com'
    );

    expect(capsule.capsuleId).toContain('capsule-');
    expect(capsule.artifactId).toBe(digest.artifactId);
    expect(capsule.playbackSecond).toBe(25);
    expect(capsule.activeSegmentId).toBe('seg-02');
    expect(capsule.targetAnchorSelector).toBe('#sec-lockfree-ringbuffer');
    expect(capsule.sourceDevice).toBe('Smart Watch');
    expect(capsule.continuationQrUrl).toContain('https://myrm.example.com');
  });

  it('校验流转胶囊的时效性', () => {
    const digest = getDefaultMockAudioDigest();
    const capsule = createContinuationCapsule(digest, 10);

    expect(isCapsuleValid(capsule)).toBe(true);

    // 模拟过期胶囊 (创建时间为 1 小时前)
    const expiredCapsule = {
      ...capsule,
      createdAtTimestamp: Date.now() - 3600 * 1000,
    };
    expect(isCapsuleValid(expiredCapsule, 600)).toBe(false);
  });

  it('默认测试音频简报包含完整结构', () => {
    const digest = getDefaultMockAudioDigest();
    expect(digest.artifactId).toBe('art-09-distributed-gateway-architecture');
    expect(digest.segments).toHaveLength(4);
    expect(digest.totalDurationSeconds).toBe(80);
    expect(digest.summaryHighlight).toBeDefined();
  });
});
