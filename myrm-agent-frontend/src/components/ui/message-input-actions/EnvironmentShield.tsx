'use client';

import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import useChatStore from '@/store/useChatStore';
import { ShieldAlert } from 'lucide-react';

const KNOWN_CATEGORIES = ['network_blocked', 'sandbox_ro'] as const;

const EnvironmentShield = () => {
  const t = useTranslations('chat.environmentAlert');
  const alerts = useChatStore((s) => s.environmentAlerts);

  const activeAlerts = KNOWN_CATEGORIES.filter((c) => alerts.has(c));
  const isHealthy = activeAlerts.length === 0;

  if (isHealthy) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-1 cursor-default">
            <ShieldAlert size={16} className="text-amber-500 animate-pulse" />
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="font-medium text-xs mb-1">{t('title')}</p>
          <ul className="text-xs space-y-0.5">
            {activeAlerts.map((category) => (
              <li key={category} className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                {t(category)}
              </li>
            ))}
          </ul>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default EnvironmentShield;
