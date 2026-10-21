import { describe, it, expect, beforeEach } from 'vitest';
import { useSideChatStore } from '../useSideChatStore';
import { formatSteeringQueueForMainAgent } from '../sideChatEngine';

describe('sideChatIntegration', () => {
  beforeEach(() => {
    useSideChatStore.getState().reset();
  });

  it('全链路：主任务推进 -> 支线问答协作者秒回 -> 增量微调无阻塞排队 -> 步间平滑吸收全闭环', () => {
    const store = useSideChatStore.getState();

    // 1. 主任务初始为第 2 步运行中
    expect(store.mainTask.currentStep).toBe(2);
    expect(store.mainTask.status).toBe('running');

    // 2. 用户在支线对话询问进度
    store.sendSideMessage('现在进行到哪一步了？');
    const stateAfterInquiry = useSideChatStore.getState();
    expect(stateAfterInquiry.messages.length).toBe(2);
    expect(stateAfterInquiry.messages[0]?.steeringStatus).toBe('instant_answered');
    expect(stateAfterInquiry.steeringQueue.length).toBe(0); // 问答不进队列

    // 3. 用户在支线对话追加两条需求（增量功能 + 参数覆写）
    store.sendSideMessage('顺手增加 Excel 导出功能');
    store.sendSideMessage('把工时计算系数修改为 1.25');

    const stateAfterFeatures = useSideChatStore.getState();
    expect(stateAfterFeatures.steeringQueue.length).toBe(2);
    expect(stateAfterFeatures.steeringQueue.every((i) => i.status === 'pending')).toBe(true);

    // 4. 验证生成的注入系统提示词格式合规
    const injectedPrompt = formatSteeringQueueForMainAgent(stateAfterFeatures.steeringQueue);
    expect(injectedPrompt).toContain('【非阻塞支线补充调优指令 (Steering Injection)】');
    expect(injectedPrompt).toContain('[增量需求] 顺手增加 Excel 导出功能');
    expect(injectedPrompt).toContain('[参数覆写] 把工时计算系数修改为 1.25');

    // 5. 主任务步进推进至第 3 步，触发平滑吸收
    store.updateMainTaskProgress({
      currentStep: 3,
      currentStepDescription: '正在组装 Excel 导出器与动态工时计算器...',
    });
    const consumed = store.consumeSteeringInNextStep(3);

    expect(consumed.length).toBe(2);
    const finalState = useSideChatStore.getState();
    expect(finalState.steeringQueue.every((i) => i.status === 'consumed')).toBe(true);
    expect(finalState.steeringQueue.every((i) => i.consumedAtStep === 3)).toBe(true);
    expect(
      finalState.messages.filter((m) => m.steeringStatus === 'injected_to_main').length
    ).toBe(2);

    // 6. 系统广播确认
    const sysMsg = finalState.messages.find((m) => m.role === 'system');
    expect(sysMsg).toBeDefined();
    expect(sysMsg?.content).toContain('在第 3 步已成功吸收并合入 2 条支线微调指令');
  });
});
