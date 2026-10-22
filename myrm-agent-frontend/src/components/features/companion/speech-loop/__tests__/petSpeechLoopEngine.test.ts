import { describe, it, expect } from 'vitest';
import {
  advanceStepStage,
  buildApprovalActionPayload,
  decomposeSpeechPrompt,
  deriveBubbleMessage,
  derivePetMoodByPhase,
} from '../petSpeechLoopEngine';
import { LoopTaskStep } from '../petSpeechLoopTypes';

describe('petSpeechLoopEngine', () => {
  it('正确将用户语音指令拆解为四阶（Plan-Code-Exec-Verify）任务步骤', () => {
    const steps = decomposeSpeechPrompt('帮我搭一个电商对账后台');

    expect(steps).toHaveLength(4);
    expect(steps[0].stage).toBe('plan');
    expect(steps[1].stage).toBe('code');
    expect(steps[2].stage).toBe('exec');
    expect(steps[3].stage).toBe('verify');

    expect(steps[0].detail).toContain('电商对账后台');
    expect(steps.every((s) => s.status === 'pending')).toBe(true);
  });

  it('在指令为空时回退至安全默认任务名', () => {
    const steps = decomposeSpeechPrompt('   ');
    expect(steps).toHaveLength(4);
    expect(steps[0].detail).toContain('通用自动化任务');
  });

  it('准确推导各阶段对应的桌宠心情', () => {
    expect(derivePetMoodByPhase('idle')).toBe('calm');
    expect(derivePetMoodByPhase('listening')).toBe('listening');
    expect(derivePetMoodByPhase('planning')).toBe('thinking');
    expect(derivePetMoodByPhase('coding')).toBe('coding');
    expect(derivePetMoodByPhase('executing')).toBe('coding');
    expect(derivePetMoodByPhase('reviewing')).toBe('alert');
    expect(derivePetMoodByPhase('completed')).toBe('celebrating');
  });

  it('准确推导各阶段对应的头顶气泡提示语并适度截断长指令', () => {
    expect(deriveBubbleMessage('idle')).toBeNull();
    expect(deriveBubbleMessage('listening')).toContain('我在听');
    expect(
      deriveBubbleMessage('planning', '这是一个超过十五个字符的超长重构任务指令')
    ).toContain('...');
    expect(deriveBubbleMessage('coding')).toContain('敲键盘');
    expect(deriveBubbleMessage('executing')).toContain('沙箱环境');
    expect(deriveBubbleMessage('reviewing')).toContain('抽屉拍板确认');
    expect(deriveBubbleMessage('completed')).toContain('顺利交付');
  });

  it('正确评估风险等级并构建拍板动作载荷', () => {
    const normalSteps: LoopTaskStep[] = [
      {
        id: 's1',
        stage: 'code',
        title: '样式修改',
        detail: '调整间距',
        status: 'pending',
      },
    ];
    const lowRiskPayload = buildApprovalActionPayload(
      '调整按钮颜色',
      normalSteps
    );
    expect(lowRiskPayload.riskLevel).toBe('low');
    expect(lowRiskPayload.status).toBe('pending');
    expect(lowRiskPayload.proposedFiles.length).toBeGreaterThan(0);

    const highRiskSteps: LoopTaskStep[] = [
      {
        id: 's2',
        stage: 'exec',
        title: '清空数据库表',
        detail: '执行删除命令',
        status: 'pending',
      },
    ];
    const highRiskPayload = buildApprovalActionPayload(
      '重置所有配置',
      highRiskSteps
    );
    expect(highRiskPayload.riskLevel).toBe('high');
  });

  it('正确更新指定阶段的执行状态与耗时毫秒数', () => {
    const initialSteps = decomposeSpeechPrompt('快速重构');
    const updated = advanceStepStage(initialSteps, 'plan', 'completed', 380);

    const planStep = updated.find((s) => s.stage === 'plan');
    expect(planStep?.status).toBe('completed');
    expect(planStep?.durationMs).toBe(380);

    const codeStep = updated.find((s) => s.stage === 'code');
    expect(codeStep?.status).toBe('pending');
  });
});
