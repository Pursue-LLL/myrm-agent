'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';
import type { SearchDepth } from '@/store/chat/types';

const DeepSearchIcon = ({ className }: { className?: string }) => (
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
    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
  </svg>
);

const DeepSearchToggle = () => {
  const t = useTranslations('mode');
  const actionMode = useChatStore((s) => s.actionMode);
  const searchDepth = useChatStore((s) => s.searchDepth);
  const setSearchDepth = useChatStore((s) => s.setSearchDepth);

  if (actionMode !== 'fast') return null;

  const isDeep = searchDepth === 'deep';

  const toggle = () => {
    const next: SearchDepth = isDeep ? 'normal' : 'deep';
    setSearchDepth(next);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={t('deepSearchTitle')}
            aria-pressed={isDeep}
            onClick={toggle}
            className={cn(
              'relative flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-300 cursor-pointer select-none',
              isDeep
                ? 'bg-primary/10 dark:bg-primary/15 text-primary border border-primary/30 dark:border-primary/25'
                : 'bg-black/[0.04] dark:bg-white/[0.06] text-black/40 dark:text-white/40 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.08] dark:hover:bg-white/[0.1]',
            )}
          >
            <DeepSearchIcon
              className={cn('transition-colors duration-300', isDeep ? 'text-primary' : 'text-current')}
            />
            <span className="hidden xl:inline">{t('deepSearchLabel')}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-56 p-3">
          <p className="font-semibold text-sm mb-1">{t('deepSearchTitle')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('deepSearchDescription')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default DeepSearchToggle;
