import {
  ApprovalAction,
  FourStagePhase,
  LoopPhase,
  LoopTaskStep,
  PetMood,
} from './petSpeechLoopTypes';

/**
 * 根据用户语音诉求分解为标准的 Plan-Code-Exec-Verify 四阶任务流
 */
export function decomposeSpeechPrompt(prompt: string): LoopTaskStep[] {
  const cleanPrompt = prompt.trim() || '通用自动化任务';

  return [
    {
      id: `step-plan-${Date.now()}`,
      stage: 'plan',
      title: '自主规划与依赖梳理',
      detail: `解析需求「${cleanPrompt}」，定位受影响文件与核心架构边界`,
      status: 'pending',
    },
    {
      id: `step-code-${Date.now()}`,
      stage: 'code',
      title: '增量代码生成与手术刀式补丁',
      detail: '根据既定规范编写高内聚模块与类型接口，杜绝全局随机漂移',
      status: 'pending',
    },
    {
      id: `step-exec-${Date.now()}`,
      stage: 'exec',
      title: '本地沙箱构建与并发执行',
      detail: '在隔离容器中跑通全量编译、类型推导与运行时挂载',
      status: 'pending',
    },
    {
      id: `step-verify-${Date.now()}`,
      stage: 'verify',
      title: '自动化测试门禁与质量自检',
      detail: '执行 Vitest 单元测试与 oxlint 静态代码巡检',
      status: 'pending',
    },
  ];
}

/**
 * 根据阶段推导桌宠心情
 */
export function derivePetMoodByPhase(phase: LoopPhase): PetMood {
  switch (phase) {
    case 'listening': {
      return 'listening';
    }
    case 'planning': {
      return 'thinking';
    }
    case 'coding':
    case 'executing': {
      return 'coding';
    }
    case 'reviewing': {
      return 'alert';
    }
    case 'completed': {
      return 'celebrating';
    }
    case 'idle':
    default: {
      return 'calm';
    }
  }
}

/**
 * 根据当前阶段推导头顶气泡文案
 */
export function deriveBubbleMessage(
  phase: LoopPhase,
  prompt?: string
): string | null {
  switch (phase) {
    case 'listening': {
      return '我在听，请随时说出你的想法…';
    }
    case 'planning': {
      return prompt
        ? `正在为你规划方案：「${prompt.slice(0, 15)}${prompt.length > 15 ? '...' : ''}」`
        : '正在梳理执行步骤与架构计划…';
    }
    case 'coding': {
      return '正在敲键盘生成增量代码与类型定义…';
    }
    case 'executing': {
      return '沙箱环境正在编译并执行最新构建…';
    }
    case 'reviewing': {
      return '关键步骤已就绪，请在侧边抽屉拍板确认！';
    }
    case 'completed': {
      return '任务已全流程顺利交付，点击查看详情！';
    }
    case 'idle':
    default: {
      return null;
    }
  }
}

/**
 * 构造默认拍板动作载荷
 */
export function buildApprovalActionPayload(
  prompt: string,
  steps: LoopTaskStep[]
): ApprovalAction {
  const hasHighRisk = steps.some(
    (s) =>
      s.title.includes('数据库') ||
      s.title.includes('删除') ||
      prompt.includes('重置')
  );

  return {
    id: `approval-${Date.now()}`,
    summary: `基于「${prompt.trim() || '未命名任务'}」的四阶流水线即将落地`,
    riskLevel: hasHighRisk ? 'high' : 'low',
    proposedFiles: [
      'src/components/features/core.tsx',
      'src/components/features/types.ts',
      'src/tests/integration.test.ts',
    ],
    status: 'pending',
  };
}

/**
 * 四阶状态推进辅助计算
 */
export function advanceStepStage(
  steps: LoopTaskStep[],
  targetStage: FourStagePhase,
  status: 'running' | 'completed' | 'failed',
  durationMs?: number
): LoopTaskStep[] {
  return steps.map((step) => {
    if (step.stage === targetStage) {
      return {
        ...step,
        status,
        ...(durationMs !== undefined ? { durationMs } : {}),
      };
    }
    return step;
  });
}
