'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';

// A custom, modern icon representing a workflow/DAG (Directed Acyclic Graph)
const WorkflowIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={cn('shrink-0', className)}
  >
    <rect x="2" y="9" width="6" height="6" rx="1.5" />
    <rect x="16" y="3" width="6" height="6" rx="1.5" />
    <rect x="16" y="15" width="6" height="6" rx="1.5" />
    <path d="M8 12h4" />
    <path d="M12 12v-6h4" />
    <path d="M12 12v6h4" />
  </svg>
);

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
            <WorkflowIcon
              className={cn('transition-all duration-500 z-10', isWorkflowMode ? 'text-primary scale-110 drop-shadow-sm' : 'text-current scale-100')}
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
