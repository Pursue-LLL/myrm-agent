'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { TaskStatus, TaskDiagnostic } from '@/services/kanban';
import { DIAGNOSTIC_SEVERITY_STYLES } from './kanban-styles';

interface KanbanDiagnosticsSectionProps {
  diagnostics: TaskDiagnostic[];
  onMove: (status: TaskStatus) => void;
  onFocusComment: () => void;
}

export default function KanbanDiagnosticsSection({
  diagnostics,
  onMove,
  onFocusComment,
}: KanbanDiagnosticsSectionProps) {
  const t = useTranslations('kanban');

  if (diagnostics.length === 0) return null;

  return (
    <section className="space-y-1.5">
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t('diagnostics')}</h4>
      {diagnostics.map((diag, idx) => {
        const sevStyle = DIAGNOSTIC_SEVERITY_STYLES[diag.severity];
        return (
          <div
            key={`${diag.rule_id}-${idx}`}
            className={cn('rounded-lg border px-3 py-2', sevStyle?.badge ?? 'bg-muted text-muted-foreground')}
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-[10px] font-semibold uppercase">{diag.severity}</span>
              <span className="text-xs font-medium">{diag.title}</span>
            </div>
            <p className="text-[10px] opacity-80">{diag.detail}</p>
            {diag.actions.length > 0 && (
              <div className="flex gap-1.5 mt-1.5">
                {diag.actions.map((action) => (
                  <button
                    key={action.kind}
                    onClick={() => {
                      if (action.kind === 'comment') {
                        onFocusComment();
                      } else if (action.payload.target_status) {
                        onMove(action.payload.target_status as TaskStatus);
                      }
                    }}
                    className={cn(
                      'text-[10px] px-2 py-0.5 rounded-full transition-colors font-medium',
                      action.suggested
                        ? 'bg-background/80 hover:bg-background text-foreground'
                        : 'bg-background/40 hover:bg-background/60 text-foreground/70',
                    )}
                  >
                    {t(`diagAction.${action.kind}` as Parameters<typeof t>[0])}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
