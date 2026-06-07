'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { IconLoader, IconGlobe } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import useConfigStore from '@/store/useConfigStore';
import { CommandSettings } from '../../CommandSettings';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import TimezoneSelector from '../system/TimezoneSelector';
import MemorySection from '../knowledge/MemorySection';

const PersonalizationSection = memo(() => {
  const t = useTranslations('settings');
  const tCommon = useTranslations('common');

  const { systemInstructions, setSystemInstructions, timezone, setTimezone, initConfig } = useConfigStore();

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [localSystemInstructions, setLocalSystemInstructions] = useState('');

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

  useEffect(() => {
    setLocalSystemInstructions(systemInstructions);
  }, [systemInstructions]);

  const handleSave = async (value: string) => {
    setIsSaving(true);
    try {
      setSystemInstructions(value);
    } finally {
      setTimeout(() => setIsSaving(false), 500);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-10 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* User instructions */}
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{t('userInstructions')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('userInstructionsPlaceholder')}</p>
        </div>
        <div className="relative">
          <textarea
            value={localSystemInstructions}
            onChange={(e) => setLocalSystemInstructions(e.target.value)}
            placeholder={t('userInstructionsPlaceholder')}
            maxLength={1000}
            rows={5}
            className={cn(
              'w-full px-4 py-3 rounded-xl resize-none',
              'bg-accent/30 border border-border/50',
              'text-sm text-foreground placeholder:text-muted-foreground/50',
              'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
              'transition-all duration-200',
            )}
          />
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-muted-foreground">{localSystemInstructions.length} / 1000</span>
            <button
              onClick={() => handleSave(localSystemInstructions)}
              disabled={isSaving || localSystemInstructions === systemInstructions}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {isSaving ? <IconLoader className="w-3.5 h-3.5 animate-spin" /> : tCommon('save')}
            </button>
          </div>
        </div>
      </div>

      <div className="border-t border-border/50" />

      {/* Timezone */}
      <div className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <IconGlobe className="w-5 h-5" />
            {t('timezone')}
          </h2>
          <p className="text-sm text-muted-foreground mt-1">{t('timezoneDescription')}</p>
        </div>
        <TimezoneSelector value={timezone || getBrowserTimezone()} onChange={setTimezone} />
      </div>

      <div className="border-t border-border/50" />

      {/* Memory management */}
      <MemorySection />

      <div className="border-t border-border/50" />

      {/* Commands */}
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">{t('commands.title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('commands.description')}</p>
        </div>
        <CommandSettings />
      </div>
    </div>
  );
});

PersonalizationSection.displayName = 'PersonalizationSection';

export default PersonalizationSection;
