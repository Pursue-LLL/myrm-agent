/**
 * [INPUT]
 * - ./utils::{linkifyErrorText, WARNING_NOTICE} (POS: 错误文本链接化与警告色)
 * - @/store/chat/types::RecoveryAction (POS: 恢复操作)
 *
 * [OUTPUT]
 * - StepErrorPanel: 步骤的错误框：错误原文、诊断建议与恢复操作按钮。
 *
 * [POS]
 * 进度步骤的错误展示：没有字符串错误信息时不渲染；被拒绝的调用按警告配色，其余按错误配色；
 * 没有目标地址的恢复操作无处可开，不渲染成按钮；站内地址在当前页跳转，外部地址在新标签页打开。
 */

import type { TranslateFn } from '@/lib/humanize';
import { cn } from '@/lib/utils/classnameUtils';
import type { ProgressItem, RecoveryAction } from '@/store/chat/types';
import { WARNING_NOTICE, linkifyErrorText } from './utils';

interface StepErrorPanelProps {
  step: ProgressItem;
  isWarning: boolean;
  t: TranslateFn;
}

function openRecoveryAction(action: RecoveryAction): void {
  if (action.url.startsWith('/')) {
    window.location.href = action.url;
  } else {
    window.open(action.url, '_blank', 'noopener,noreferrer');
  }
}

export function StepErrorPanel({ step, isWarning, t }: StepErrorPanelProps) {
  if (!step.error || typeof step.error !== 'string') {
    return null;
  }
  const textTone = isWarning ? WARNING_NOTICE.text : 'text-destructive-text';
  const recoveryActions = (step.recovery_actions ?? []).filter((action) => action.url);

  return (
    <div
      className={cn(
        'mt-2 p-2.5 rounded-lg border',
        isWarning ? WARNING_NOTICE.box : 'bg-destructive/5 dark:bg-destructive/10 border-destructive/20',
      )}
    >
      <div className={cn('text-xs break-all leading-relaxed whitespace-pre-wrap', textTone)}>
        {linkifyErrorText(step.error)}
      </div>
      {step.error_hint && (
        <div
          className={cn(
            'mt-2 text-[11px] opacity-80 border-t pt-2 flex items-start gap-1.5 leading-relaxed',
            isWarning ? WARNING_NOTICE.rule : 'border-destructive/10',
          )}
        >
          <span className={cn('font-bold shrink-0', textTone)}>{t('diagnosticHint')}:</span>
          <span className="italic text-foreground/80">{step.error_hint}</span>
        </div>
      )}

      {recoveryActions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {recoveryActions.map((action, idx) => {
            const isPrimary = action.id === 'top_up' || action.id.includes('install') || action.id.includes('mock');

            return (
              <button
                key={idx}
                onClick={(e) => {
                  e.stopPropagation();
                  openRecoveryAction(action);
                }}
                className={cn(
                  'inline-flex items-center justify-center rounded-full text-[11px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 h-6 px-2.5',
                  isPrimary
                    ? 'bg-primary text-primary-foreground shadow hover:bg-primary/90'
                    : 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
                )}
              >
                {action.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
