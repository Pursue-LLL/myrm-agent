/**
 * companionPlanHubEngine.ts
 * 桌面伴侣迷你计划抽屉、任务进度计算与成果气泡纯函数引擎
 */

import type {
  MicroPlanDraft,
  PlanSubtaskItem,
  PlanSubtaskStatus,
} from './companionPlanHubTypes';

export function calculatePlanProgress(subtasks: PlanSubtaskItem[]): {
  completed: number;
  total: number;
  skipped: number;
  percent: number;
  isAllDone: boolean;
} {
  const total = subtasks.length;
  if (total === 0) {
    return { completed: 0, total: 0, skipped: 0, percent: 100, isAllDone: true };
  }

  let completed = 0;
  let skipped = 0;

  for (const task of subtasks) {
    if (task.status === 'completed') {
      completed += 1;
    } else if (task.status === 'skipped') {
      skipped += 1;
    }
  }

  const effectiveTotal = Math.max(1, total - skipped);
  const percent = Math.min(
    100,
    Math.round((completed / effectiveTotal) * 100)
  );
  const isAllDone = completed + skipped === total;

  return { completed, total, skipped, percent, isAllDone };
}

export function formatProgressHudLabel(
  stepIndex: number,
  totalSteps: number,
  currentTitle: string
): string {
  const cleanTitle = currentTitle.trim();
  const safeTotal = Math.max(1, totalSteps);
  const safeStep = Math.min(safeTotal, Math.max(1, stepIndex));
  return `${cleanTitle} (${safeStep}/${safeTotal})`;
}

export function toggleSubtaskSkipState(
  subtasks: PlanSubtaskItem[],
  subtaskId: string
): PlanSubtaskItem[] {
  return subtasks.map((task) => {
    if (task.id !== subtaskId) {
      return task;
    }
    if (task.required) {
      // 核心必选子任务不可跳过
      return task;
    }
    const nextStatus: PlanSubtaskStatus =
      task.status === 'skipped' ? 'pending' : 'skipped';
    return { ...task, status: nextStatus };
  });
}

export function updateSubtaskStatus(
  subtasks: PlanSubtaskItem[],
  subtaskId: string,
  nextStatus: PlanSubtaskStatus
): PlanSubtaskItem[] {
  return subtasks.map((task) => {
    if (task.id === subtaskId) {
      return { ...task, status: nextStatus };
    }
    return task;
  });
}

export function formatElapsedTimeString(seconds: number): string {
  const safeSec = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safeSec / 60);
  const remSec = safeSec % 60;
  const padMin = String(mins).padStart(2, '0');
  const padSec = String(remSec).padStart(2, '0');
  return `${padMin}:${padSec}`;
}

export function validateMicroPlanDraft(raw: unknown): {
  valid: boolean;
  plan?: MicroPlanDraft;
  error?: string;
} {
  if (typeof raw !== 'object' || raw === null) {
    return { valid: false, error: '计划数据必须是合法对象' };
  }

  const rec = raw as Record<string, unknown>;

  if (typeof rec.planId !== 'string' || rec.planId.trim() === '') {
    return { valid: false, error: '缺少计划唯一标识 (planId)' };
  }

  if (typeof rec.goal !== 'string' || rec.goal.trim() === '') {
    return { valid: false, error: '缺少计划目标 (goal)' };
  }

  if (!Array.isArray(rec.subtasks)) {
    return { valid: false, error: '子任务列表必须是数组 (subtasks)' };
  }

  const subtasks: PlanSubtaskItem[] = [];
  for (const item of rec.subtasks) {
    if (typeof item === 'object' && item !== null) {
      const taskObj = item as Record<string, unknown>;
      subtasks.push({
        id: String(taskObj.id ?? `task-${Date.now()}`),
        title: String(taskObj.title ?? '未命名子任务'),
        description:
          typeof taskObj.description === 'string'
            ? taskObj.description
            : undefined,
        status: (taskObj.status as PlanSubtaskStatus) ?? 'pending',
        required: Boolean(taskObj.required ?? false),
        order: typeof taskObj.order === 'number' ? taskObj.order : 0,
      });
    }
  }

  const plan: MicroPlanDraft = {
    planId: String(rec.planId),
    goal: String(rec.goal),
    targetAgentName: String(rec.targetAgentName ?? 'Myrm 调度助手'),
    subtasks,
    estimatedMinutes:
      typeof rec.estimatedMinutes === 'number' ? rec.estimatedMinutes : 5,
    createdAt: typeof rec.createdAt === 'number' ? rec.createdAt : Date.now(),
  };

  return { valid: true, plan };
}
