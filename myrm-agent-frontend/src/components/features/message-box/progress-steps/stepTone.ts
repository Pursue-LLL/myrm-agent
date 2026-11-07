/**
 * [INPUT]
 * - @/store/chat/types::ProgressItem (POS: 进度步骤)
 * - ./utils::getDisplayStatus (POS: 步骤展示状态，拒绝类调用按警告展示)
 *
 * [OUTPUT]
 * - StepVisualState / getStepVisualState: 步骤的视觉状态判定。
 * - stepTitleTone / progressTextTone: 视觉状态与通知等级对应的文字色。
 *
 * [POS]
 * 进度步骤「状态 → 颜色」的唯一来源：展开的树节点与折叠摘要共用同一套判定与文字色。
 * 文字一律用 destructive-text 令牌（暗色下提亮），填充色令牌 destructive 只用于背景与边框。
 */

import type { ProgressItem } from '@/store/chat/types';
import { getDisplayStatus } from './utils';

/** How a step is drawn. When several hold, the first of warning, blocked, error, in flight, completed wins. */
export interface StepVisualState {
  isWarning: boolean;
  isBlocked: boolean;
  isError: boolean;
  isCurrent: boolean;
  isCompleted: boolean;
}

export function getStepVisualState(step: ProgressItem, isCurrent: boolean): StepVisualState {
  const isWarning = getDisplayStatus(step) === 'warning';
  const isBlocked = step.status === 'blocked';
  return {
    isWarning,
    isBlocked,
    isError: Boolean(step.error) && !isWarning && !isBlocked,
    isCurrent,
    isCompleted: !step.error && !isCurrent,
  };
}

/** Title colour of a step; `idle` is the colour of a step that is neither amber nor in error. */
export const stepTitleTone = ({ isWarning, isBlocked, isError }: StepVisualState, idle: string): string => {
  if (isWarning || isBlocked) {
    return 'text-amber-600 dark:text-amber-400';
  }
  return isError ? 'text-destructive-text' : idle;
};

/** Colour of a step's progress percentage by notify level. */
export const progressTextTone = (level: ProgressItem['notify_level']): string => {
  if (level === 'alert') {
    return 'text-destructive-text';
  }
  return level === 'warn' ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground/60';
};
