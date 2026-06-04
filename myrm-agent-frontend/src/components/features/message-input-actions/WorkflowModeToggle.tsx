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
              'relative flex items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium transition-all duration-300 cursor-pointer select-none',
              isWorkflowMode
                ? 'bg-primary/10 dark:bg-primary/15 text-primary border border-primary/30 dark:border-primary/25 shadow-[0_0_10px_rgba(var(--primary),0.2)]'
                : 'bg-black/[0.04] dark:bg-white/[0.06] text-black/40 dark:text-white/40 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.08] dark:hover:bg-white/[0.1]',
            )}
          >
            <WorkflowIcon
              className={cn('transition-colors duration-300', isWorkflowMode ? 'text-primary' : 'text-current')}
            />
            <span className="hidden sm:inline">{t('workflowModeLabel')}</span>
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
