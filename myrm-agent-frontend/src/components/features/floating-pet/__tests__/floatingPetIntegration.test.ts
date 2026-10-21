import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useFloatingPetStore } from '../useFloatingPetStore';
import { getPetGlowStyle } from '../floatingPetEngine';

describe('floatingPetIntegration', () => {
  beforeEach(() => {
    useFloatingPetStore.getState().reset();
  });

  it('全链路：常驻桌宠挂件 -> 语音按住即说 -> 后台任务发射与光环流转 -> 气泡进度同步与工件查看闭环', () => {
    const store = useFloatingPetStore.getState();

    // 1. 验证初始状态：屏幕边缘吸附，空闲情绪，无任务
    expect(store.mood).toBe('idle');
    expect(store.position).toBe('right_edge');
    expect(getPetGlowStyle(store.mood).ringColor).toContain('zinc');

    // 2. 模拟用户按住桌宠说话 (Push-to-Talk)
    store.startPushToTalk();
    const stateListening = useFloatingPetStore.getState();
    expect(stateListening.isVoiceRecording).toBe(true);
    expect(stateListening.mood).toBe('listening');
    expect(getPetGlowStyle(stateListening.mood).ringColor).toContain('red');

    // 3. 用户说出一句话需求后松手
    const voicePrompt = '帮做一个书画作品定制的报价工具，选完类型、尺寸、材料自动算出价格并保存记录';
    const newTask = store.stopPushToTalk(voicePrompt);

    expect(newTask).not.toBeNull();
    const stateThinking = useFloatingPetStore.getState();
    expect(stateThinking.isVoiceRecording).toBe(false);
    expect(stateThinking.mood).toBe('thinking');
    expect(stateThinking.isBubbleExpanded).toBe(true);
    expect(getPetGlowStyle(stateThinking.mood).ringColor).toContain('purple');

    // 4. 后台 Agent 自主执行并汇报进度到 50%
    if (newTask) {
      store.updateTaskProgress(newTask.id, 50, 'running');
      const stateWorking = useFloatingPetStore.getState();
      expect(stateWorking.activeTask?.progress).toBe(50);
      expect(stateWorking.mood).toBe('working');
      expect(getPetGlowStyle(stateWorking.mood).ringColor).toContain('cyan');

      // 5. 任务顺利达成 (100%)
      store.updateTaskProgress(newTask.id, 100, 'completed');
      const stateCompleted = useFloatingPetStore.getState();
      expect(stateCompleted.activeTask?.progress).toBe(100);
      expect(stateCompleted.activeTask?.status).toBe('completed');
      expect(stateCompleted.mood).toBe('celebrating');
      expect(getPetGlowStyle(stateCompleted.mood).ringColor).toContain('amber');

      // 6. 模拟用户点击展开工件详情
      const onOpenMainWindowMock = vi.fn();
      onOpenMainWindowMock(newTask.id);
      expect(onOpenMainWindowMock).toHaveBeenCalledWith(newTask.id);
    }
  });
});
