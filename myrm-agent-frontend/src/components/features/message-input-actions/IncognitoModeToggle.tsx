'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';
import { useRouter, usePathname } from 'next/navigation';

const IncognitoIcon = ({ className }: { className?: string }) => (
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
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
    <line x1="2" y1="2" x2="22" y2="22" />
  </svg>
);

const IncognitoModeToggle = () => {
  const t = useTranslations('memory');
  const router = useRouter();
  const pathname = usePathname();
  const incognitoMode = useChatStore((s) => s.incognitoMode);
  const setIncognitoMode = useChatStore((s) => s.setIncognitoMode);
  const messages = useChatStore((s) => s.messages);
  const initializeChat = useChatStore((s) => s.initializeChat);

  const toggle = () => {
    if (messages.length > 0) {
      if (pathname !== '/') {
        router.push('/');
      }
      initializeChat(undefined);
    }
    setIncognitoMode(!incognitoMode);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={t('incognitoMode')}
            aria-pressed={incognitoMode}
            onClick={toggle}
            className={cn(
              'relative flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-medium whitespace-nowrap transition-all duration-300 cursor-pointer select-none',
              incognitoMode
                ? 'bg-destructive/10 dark:bg-destructive/15 text-destructive border border-destructive/30 dark:border-destructive/25'
                : 'bg-black/[0.04] dark:bg-white/[0.06] text-black/40 dark:text-white/40 border border-transparent hover:text-black dark:hover:text-white hover:bg-black/[0.08] dark:hover:bg-white/[0.1]',
            )}
          >
            <IncognitoIcon
              className={cn('transition-colors duration-300', incognitoMode ? 'text-destructive' : 'text-current')}
            />
            <span className="hidden xl:inline">{t('incognitoMode')}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-56 p-3">
          <p className="font-semibold text-sm mb-1">{t('incognitoMode')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">{t('incognitoModeDesc')}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default IncognitoModeToggle;
