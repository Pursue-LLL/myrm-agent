import { describe, it, expect } from 'vitest';
import {
  finalizeInterruptedTurn,
  getBargeInVolumeThreshold,
  healContextOnBargeIn,
  normalizeWaveformHeights,
  shouldTriggerBargeIn,
} from '../duplexVoiceEngine';
import { DuplexTurnMessage } from '../duplexVoiceTypes';

describe('duplexVoiceEngine', () => {
  it('正确根据灵敏度等级映射打断音量门限', () => {
    expect(getBargeInVolumeThreshold('high')).toBe(25);
    expect(getBargeInVolumeThreshold('medium')).toBe(45);
    expect(getBargeInVolumeThreshold('low')).toBe(65);
  });

  it('仅在智能体处于 speaking 且麦克风音量达到门限时触发随时插话打断', () => {
    // speaking 状态下达到或超过门限
    expect(shouldTriggerBargeIn('speaking', 50, 'medium')).toBe(true);
    // speaking 状态下低于门限
    expect(shouldTriggerBargeIn('speaking', 30, 'medium')).toBe(false);
    // 非 speaking 状态（如 listening / idle / processing）即使音量很高也不触发打断
    expect(shouldTriggerBargeIn('listening', 80, 'medium')).toBe(false);
    expect(shouldTriggerBargeIn('idle', 90, 'medium')).toBe(false);
    expect(shouldTriggerBargeIn('processing', 80, 'medium')).toBe(false);
  });

  it('上下文自愈算法正确在指定位置截断播报并沉淀双向纠偏摘要', () => {
    const fullAgentSpeech = '我现在开始为您编写用户登录模块，使用 JWT 作为主要鉴权方式';
    const userCorrection = '换成 OAuth2 和 GitHub 第三方登录，不要账密！';

    const healed = healContextOnBargeIn(fullAgentSpeech, userCorrection, 13);

    expect(healed.active).toBe(true);
    expect(healed.interruptedAgentMessage).toBe('我现在开始为您编写用户登录');
    expect(healed.userInterruptionSnippet).toBe(userCorrection);
    expect(healed.healedContextPreview).toContain('第 13 字执行毫秒级中断');
    expect(healed.healedContextPreview).toContain('OAuth2');
  });

  it('在智能体开头发言即被打断时生成正确的边界自愈摘要', () => {
    const healed = healContextOnBargeIn('', '停一下，先别写', 0);
    expect(healed.interruptedAgentMessage).toBe('');
    expect(healed.healedContextPreview).toContain('开头发言即被即时打断');
    expect(healed.healedContextPreview).toContain('停一下，先别写');
  });

  it('能够将打断事件对齐追加为结构化的历史消息记录', () => {
    const initialMessages: DuplexTurnMessage[] = [];
    const updated = finalizeInterruptedTurn(
      initialMessages,
      '正在构建组件架构',
      '不用拆那么细，写单文件就好'
    );

    expect(updated).toHaveLength(2);
    expect(updated[0].role).toBe('agent');
    expect(updated[0].wasInterrupted).toBe(true);
    expect(updated[0].content).toBe('正在构建组件架构');

    expect(updated[1].role).toBe('user');
    expect(updated[1].content).toBe('不用拆那么细，写单文件就好');
  });

  it('波形高度归一化输出符合有效区间且中间高两边自然的柱状数组', () => {
    const heights = normalizeWaveformHeights(60, 10);
    expect(heights).toHaveLength(10);
    expect(heights.every((h) => h >= 12 && h <= 100)).toBe(true);
    // 中间位置柱状应该高于最边上
    const centerIndex = Math.floor(heights.length / 2);
    expect(heights[centerIndex]).toBeGreaterThanOrEqual(heights[0]);
  });
});
