'use client';

import { X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';

export interface WorkflowTemplateArmedBarProps {
  templateId: string;
  displayName?: string | null;
  className?: string;
}

export function WorkflowTemplateArmedBar({
  templateId,
  displayName,
  className,
}: WorkflowTemplateArmedBarProps) {
  const t = useTranslations('chat.workflowTemplateArmed');

  const handleDisarm = () => {
    const store = useChatStore.getState();
    store.clearPendingWorkflowTemplate();
    store.setIsWorkflowMode(false);
  };

  const label = displayName?.trim() || templateId;

  return (
    <div
      data-testid="workflow-template-armed-bar"
      className={cn(
        'mb-2 flex flex-wrap items-center gap-2 rounded-xl border border-primary/25 bg-primary/[0.06] px-3 py-2',
        className,
      )}
    >
      <span className="text-[11px] font-medium uppercase tracking-wide text-primary/80">{t('label')}</span>
      <span
        className="inline-flex h-6 max-w-full items-center rounded-md border border-primary/20 bg-primary/10 px-2 text-xs font-medium leading-none text-primary"
        title={templateId}
      >
        <span className="truncate">{label}</span>
      </span>
      <button
        type="button"
        onClick={handleDisarm}
        className="ml-auto inline-flex h-6 items-center gap-1 rounded-md border border-border/60 px-2 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        aria-label={t('disarm')}
      >
        <X size={12} />
        {t('disarm')}
      </button>
    </div>
  );
}
