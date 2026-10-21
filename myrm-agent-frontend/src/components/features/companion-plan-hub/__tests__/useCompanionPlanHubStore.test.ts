import { beforeEach, describe, expect, it } from 'vitest';
import { useCompanionPlanHubStore } from '../useCompanionPlanHubStore';
import type { MicroPlanDraft, MiniArtifactSummary } from '../companionPlanHubTypes';

describe('useCompanionPlanHubStore', () => {
  beforeEach(() => {
    useCompanionPlanHubStore.getState().resetAll();
  });

  it('初始状态规范且支持重置', () => {
    const state = useCompanionPlanHubStore.getState();
    expect(state.displayMode).toBe('pet_only');
    expect(state.activePlan).toBeNull();
    expect(state.executionProgress).toBeNull();
    expect(state.completedArtifact).toBeNull();
  });

  it('设置活动计划并同步微调目标与模式', () => {
    const plan: MicroPlanDraft = {
      planId: 'plan-test',
      goal: '开发自动化测试',
      targetAgentName: '测试专员',
      estimatedMinutes: 5,
      createdAt: Date.now(),
      subtasks: [
        { id: 'st-1', title: '编写用例', status: 'pending', required: true, order: 1 },
        { id: 'st-2', title: '执行用例', status: 'pending', required: false, order: 2 },
      ],
    };

    useCompanionPlanHubStore.getState().setActivePlan(plan);
    const state = useCompanionPlanHubStore.getState();
    expect(state.activePlan?.planId).toBe('plan-test');
    expect(state.refinedGoal).toBe('开发自动化测试');
    expect(state.displayMode).toBe('plan_drawer');

    useCompanionPlanHubStore.getState().setRefinedGoal('微调后的业务目标');
    expect(useCompanionPlanHubStore.getState().refinedGoal).toBe('微调后的业务目标');
  });

  it('切换子任务跳过状态', () => {
    const plan: MicroPlanDraft = {
      planId: 'plan-skip-test',
      goal: '测试跳过',
      targetAgentName: '助手',
      estimatedMinutes: 3,
      createdAt: Date.now(),
      subtasks: [
        { id: 'req-1', title: '必选步骤', status: 'pending', required: true, order: 1 },
        { id: 'opt-2', title: '可选步骤', status: 'pending', required: false, order: 2 },
      ],
    };

    useCompanionPlanHubStore.getState().setActivePlan(plan);
    useCompanionPlanHubStore.getState().toggleSubtaskSkip('opt-2');

    const subtasks = useCompanionPlanHubStore.getState().activePlan?.subtasks ?? [];
    expect(subtasks[1].status).toBe('skipped');
  });

  it('确认开工切换进入进度 HUD 模式并初始化执行状态', () => {
    const plan: MicroPlanDraft = {
      planId: 'plan-launch',
      goal: '开工目标',
      targetAgentName: '助手',
      estimatedMinutes: 5,
      createdAt: Date.now(),
      subtasks: [
        { id: 's1', title: '步骤一', status: 'pending', required: true, order: 1 },
      ],
    };

    useCompanionPlanHubStore.getState().setActivePlan(plan);
    useCompanionPlanHubStore.getState().confirmStartPlan();

    const state = useCompanionPlanHubStore.getState();
    expect(state.displayMode).toBe('progress_hud');
    expect(state.executionProgress).not.toBeNull();
    expect(state.executionProgress?.currentStepIndex).toBe(1);
    expect(state.executionProgress?.currentStepTitle).toBe('步骤一');
  });

  it('追加执行日志与完工成果卡片设置', () => {
    useCompanionPlanHubStore.getState().setExecutionProgress({
      currentStepIndex: 2,
      totalSteps: 3,
      currentStepTitle: '生成工件',
      elapsedSeconds: 30,
      logs: ['初始化'],
    });

    useCompanionPlanHubStore.getState().appendProgressLog('步骤执行成功');
    expect(
      useCompanionPlanHubStore.getState().executionProgress?.logs
    ).toContain('步骤执行成功');

    const artifact: MiniArtifactSummary = {
      artifactId: 'art-1',
      title: '店长经营看板工件',
      summaryText: '已生成单文件交互工件并通过验证',
      completedAt: Date.now(),
    };

    useCompanionPlanHubStore.getState().setCompletedArtifact(artifact);
    const state = useCompanionPlanHubStore.getState();
    expect(state.completedArtifact?.artifactId).toBe('art-1');
    expect(state.displayMode).toBe('artifact_bubble');
  });
});
