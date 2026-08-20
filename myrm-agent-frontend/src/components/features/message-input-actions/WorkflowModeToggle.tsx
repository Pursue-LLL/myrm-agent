'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';
import { IconWorkflow } from '@/components/features/icons/PremiumIcons';

const WorkflowModeToggle = () => {
  const t = useTranslations('mode');
  const isWorkflowMode = useChatStore((s) => s.isWorkflowMode);
  const setIsWorkflowMode = useChatStore((s) => s.setIsWorkflowMode);

  const toggle = () => {
    setIsWorkflowMode(!isWorkflowMode);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={t('workflowModeTitle')}
            aria-pressed={isWorkflowMode}
            onClick={toggle}
            className={cn(
              'relative flex shrink-0 items-center gap-1.5 h-7 px-3 rounded-full text-xs font-semibold whitespace-nowrap transition-all duration-500 cursor-pointer select-none overflow-hidden',
              isWorkflowMode
                ? 'bg-gradient-to-r from-primary/20 to-primary/10 text-primary border border-primary/40 shadow-md shadow-primary/30 hover:shadow-lg hover:shadow-primary/40'
                : 'bg-black/[0.03] dark:bg-white/[0.04] text-black/50 dark:text-white/50 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.06] dark:hover:bg-white/[0.08]',
            )}
          >
            {isWorkflowMode && (
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full animate-shimmer" />
            )}
            <IconWorkflow
              className={cn(
                'shrink-0 transition-all duration-500 z-10',
                isWorkflowMode ? 'text-primary scale-110 drop-shadow-sm' : 'text-current scale-100',
              )}
            />
            <span className="hidden xl:inline z-10 tracking-wide">{t('workflowModeLabel')}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-64 p-3">
          <p className="font-semibold text-sm mb-1">{t('workflowModeTitle')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('workflowModeDescription')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default WorkflowModeToggle;
