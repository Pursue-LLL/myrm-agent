/**
 * [INPUT]
 * - ./stepTone::StepVisualState (POS: 步骤视觉状态)
 * - ./toolIcons::* (POS: 步骤图标与 agent 主题色)
 * - @/lib/humanize::TranslateFn (POS: 翻译函数类型)
 *
 * [OUTPUT]
 * - StepStatusIcon: 步骤图标，颜色随视觉状态变化。
 * - StepTitle: 步骤标题行，带 agent 徽标与「智能降级」徽标。
 *
 * [POS]
 * 进度步骤的标题构件：展开树节点与折叠摘要共用图标与标题行，只在标题文字与颜色上不同。
 */

import { Badge } from '@/components/primitives/badge';
import type { TranslateFn } from '@/lib/humanize';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem } from '@/store/chat/types';
import type { StepVisualState } from './stepTone';
import {
  AGENT_COLOR_CLASSES,
  StepIcon,
  formatAgentHandle,
  getAgentColor,
  isSystemStep,
  type AgentThemeColor,
} from './toolIcons';

/** An unknown theme colour falls back to the colour derived from the agent instance. */
const agentBadgeClass = (agentInstance: string, themeColor?: string): string =>
  (themeColor && AGENT_COLOR_CLASSES[themeColor as AgentThemeColor]?.badge) ||
  AGENT_COLOR_CLASSES[getAgentColor(agentInstance)].badge;

export function StepStatusIcon({ step, state }: { step: ProgressItem; state: StepVisualState }) {
  return (
    <StepIcon
      step_key={step.step_key}
      tool_name={step.tool_name}
      size={16}
      className={cn(
        'flex-shrink-0 transition-colors duration-200',
        state.isWarning || state.isBlocked
          ? 'text-amber-600 dark:text-amber-500'
          : state.isError
            ? 'text-destructive-text'
            : isSystemStep(step.tool_name)
              ? 'text-primary/70'
              : 'text-foreground/70',
      )}
    />
  );
}

interface StepTitleProps {
  step: ProgressItem;
  /** The localized title text. */
  title: string;
  className: string;
  t: TranslateFn;
}

export function StepTitle({ step, title, className, t }: StepTitleProps) {
  return (
    <h4 className={className}>
      {step.agent_instance && (
        <Badge
          variant="outline"
          className={cn(
            'mr-1.5 h-5 px-2 text-[10px] font-bold border hidden sm:inline-flex',
            agentBadgeClass(step.agent_instance, step.theme_color),
          )}
        >
          {formatAgentHandle(step.agent_instance, step.display_name)}
        </Badge>
      )}
      {title}
      {step.step_key === 'safety_fallback_active' && (
        <Badge
          variant="outline"
          className="ml-2 bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 text-[10px] uppercase tracking-wider font-bold"
        >
          {t('smartFallbackBadge')}
        </Badge>
      )}
    </h4>
  );
}
