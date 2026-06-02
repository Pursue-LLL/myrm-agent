'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';

import { Switch } from '@/components/ui/switch';

interface MemorySettingsTogglesProps {
  enableMemory: boolean;
  setEnableMemory: (value: boolean) => void;
  memoryRequireConfirmation: boolean;
  setMemoryRequireConfirmation: (value: boolean) => void;
  enableMemoryAutoExtraction: boolean;
  setEnableMemoryAutoExtraction: (value: boolean) => void;
  preCompactEnabled: boolean;
  setPreCompactEnabled: (value: boolean) => void;
  preCompactBudgetTokens: number;
  setPreCompactBudgetTokens: (value: number) => void;
}

const MemorySettingsToggles = memo<MemorySettingsTogglesProps>(
  ({
    enableMemory,
    setEnableMemory,
    memoryRequireConfirmation,
    setMemoryRequireConfirmation,
    enableMemoryAutoExtraction,
    setEnableMemoryAutoExtraction,
    preCompactEnabled,
    setPreCompactEnabled,
    preCompactBudgetTokens,
    setPreCompactBudgetTokens,
  }) => {
    const t = useTranslations('memory');

    return (
      <>
        <div className="flex items-center justify-between rounded-xl border border-border/50 bg-accent/30 p-4">
          <div className="flex-1 pr-4">
            <h3 className="text-sm font-medium text-foreground">{t('enableMemory')}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{t('enableMemoryDesc')}</p>
          </div>
          <Switch checked={enableMemory} onCheckedChange={setEnableMemory} />
        </div>

        {enableMemory && (
          <div className="ml-2 flex items-center justify-between rounded-xl border border-border/30 bg-accent/20 p-4">
            <div className="flex-1 pr-4">
              <h3 className="text-sm font-medium text-foreground">{t('requireConfirmation')}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{t('requireConfirmationDesc')}</p>
            </div>
            <Switch checked={memoryRequireConfirmation} onCheckedChange={setMemoryRequireConfirmation} />
          </div>
        )}

        {enableMemory && (
          <div className="ml-2 flex items-center justify-between rounded-xl border border-border/30 bg-accent/20 p-4">
            <div className="flex-1 pr-4">
              <h3 className="text-sm font-medium text-foreground">{t('autoExtraction')}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{t('autoExtractionDesc')}</p>
            </div>
            <Switch checked={enableMemoryAutoExtraction} onCheckedChange={setEnableMemoryAutoExtraction} />
          </div>
        )}

        {enableMemory && (
          <div className="ml-2 space-y-3 rounded-xl border border-border/30 bg-accent/20 p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex-1 pr-4">
                <h3 className="text-sm font-medium text-foreground">{t('preCompactEnabled')}</h3>
                <p className="mt-1 text-xs text-muted-foreground">{t('preCompactEnabledDesc')}</p>
              </div>
              <Switch checked={preCompactEnabled} onCheckedChange={setPreCompactEnabled} />
            </div>
            {preCompactEnabled && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{t('preCompactBudget')}</span>
                  <span>{preCompactBudgetTokens}</span>
                </div>
                <input
                  type="range"
                  min={800}
                  max={2000}
                  step={50}
                  value={preCompactBudgetTokens}
                  onChange={(event) => setPreCompactBudgetTokens(Number(event.target.value))}
                  className="w-full accent-primary"
                />
              </div>
            )}
          </div>
        )}
      </>
    );
  },
);

MemorySettingsToggles.displayName = 'MemorySettingsToggles';

export default MemorySettingsToggles;
