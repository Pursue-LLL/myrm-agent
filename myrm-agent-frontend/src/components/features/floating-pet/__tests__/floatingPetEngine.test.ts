import { describe, it, expect } from 'vitest';
import {
  computePetMood,
  getPetGlowStyle,
  formatVoiceTranscriptToTask,
  calculateDockPositionClasses,
} from '../floatingPetEngine';
import { PetTaskItem } from '../floatingPetTypes';

describe('floatingPetEngine', () => {
  it('根据录音状态与活跃任务派生正确的情绪状态', () => {
    // 1. 录音中优先是 listening
    expect(computePetMood(true, null)).toBe('listening');

    // 2. 无任务处于 idle
    expect(computePetMood(false, null)).toBe('idle');

    // 3. 任务刚启动 progress < 20 处于 thinking
    const thinkingTask: PetTaskItem = {
      id: 't-1',
      title: '生成报价单',
      status: 'running',
      progress: 10,
      summary: '正在分析公式',
      createdAt: Date.now(),
    };
    expect(computePetMood(false, thinkingTask)).toBe('thinking');

    // 4. 任务推进中处于 working
    const workingTask: PetTaskItem = {
      ...thinkingTask,
      progress: 50,
    };
    expect(computePetMood(false, workingTask)).toBe('working');

    // 5. 任务完成处于 celebrating
    const completedTask: PetTaskItem = {
      ...thinkingTask,
      status: 'completed',
      progress: 100,
    };
    expect(computePetMood(false, completedTask)).toBe('celebrating');
  });

  it('获取不同情绪下的 Micro-Status Ring 光环与呼吸样式', () => {
    const listeningStyle = getPetGlowStyle('listening');
    expect(listeningStyle.ringColor).toContain('red');
    expect(listeningStyle.statusLabel).toContain('倾听语音');

    const thinkingStyle = getPetGlowStyle('thinking');
    expect(thinkingStyle.ringColor).toContain('purple');

    const workingStyle = getPetGlowStyle('working');
    expect(workingStyle.ringColor).toContain('cyan');

    const celebratingStyle = getPetGlowStyle('celebrating');
    expect(celebratingStyle.ringColor).toContain('amber');

    const idleStyle = getPetGlowStyle('idle');
    expect(idleStyle.ringColor).toContain('zinc');
  });

  it('正确将一句话语音输入格式化为后台任务', () => {
    const transcript = '帮做一个书画作品定制的报价工具，自动计算价格并保存记录';
    const task = formatVoiceTranscriptToTask(transcript);

    expect(task.id).toContain('pet-task-');
    expect(task.title).toContain('帮做一个书画作品定制的报价工具');
    expect(task.status).toBe('running');
    expect(task.progress).toBe(10);
    expect(task.summary).toBe(transcript);
  });

  it('正确计算贴边吸附坐标样式', () => {
    expect(calculateDockPositionClasses('left_edge')).toContain('left-4');
    expect(calculateDockPositionClasses('bottom_right')).toContain('right-6 bottom-6');
    expect(calculateDockPositionClasses('right_edge')).toContain('right-4');
  });
});
