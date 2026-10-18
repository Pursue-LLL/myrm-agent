'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';
import { useRouter, usePathname } from 'next/navigation';
import IncognitoIcon from './IncognitoIcon';

const IncognitoModeToggle = () => {
  const t = useTranslations('memory');
  const router = useRouter();
  const pathname = usePathname();
  const incognitoMode = useChatStore((s) => s.incognitoMode);
  const setIncognitoMode = useChatStore((s) => s.setIncognitoMode);
  const initializeChat = useChatStore((s) => s.initializeChat);

  const toggle = () => {
    // Incognito is a property of the chat, not a mode the current chat can enter: the server keys every
    // removal and export decision off the chat row's `is_incognito`, and a chat that already has a row can
    // never become one. Switching always starts a fresh chat, whose first message is what gives the row its
    // flag — so an id that predates the switch can never end up bound to an upload it will not outlive.
    if (pathname !== '/') {
      router.push('/');
    }
    initializeChat(undefined);
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
