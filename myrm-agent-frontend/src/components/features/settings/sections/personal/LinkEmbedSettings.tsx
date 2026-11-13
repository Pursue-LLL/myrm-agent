'use client';

import { useId } from 'react';
import { useTranslations } from 'next-intl';
import { BulbIcon } from 'hugeicons-react';
import useEmbedConsentStore, { type EmbedMode } from '@/store/useEmbedConsentStore';
import SettingsSection from '../SettingsSection';

/** Whether links in chat load rich embeds: the mode select and the providers already allowed. */
export default function LinkEmbedSettings() {
  const t = useTranslations('settings');
  const titleId = useId();
  const descriptionId = useId();
  const embedMode = useEmbedConsentStore((s) => s.embedMode);
  const setEmbedMode = useEmbedConsentStore((s) => s.setEmbedMode);
  const allowedProviders = useEmbedConsentStore((s) => s.allowedProviders);
  const clearAllowed = useEmbedConsentStore((s) => s.clearAllowed);

  return (
    <SettingsSection title={t('linkEmbeds')}>
      <div className="flex flex-col space-y-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 shrink-0 rounded-lg bg-primary/10 p-2 text-primary">
            <BulbIcon size={18} />
          </div>
          <div className="min-w-0 flex-1 space-y-2">
            <div>
              <p id={titleId} className="text-sm font-medium text-foreground">
                {t('linkEmbedsMode')}
              </p>
              <p id={descriptionId} className="text-xs text-muted-foreground">
                {t('linkEmbedsDesc')}
              </p>
            </div>
            <select
              value={embedMode}
              onChange={(e) => setEmbedMode(e.target.value as EmbedMode)}
              aria-labelledby={titleId}
              aria-describedby={descriptionId}
              className="rounded-lg border border-border/60 bg-background px-3 py-2 text-sm"
            >
              <option value="ask">{t('linkEmbedsAsk')}</option>
              <option value="always">{t('linkEmbedsAlways')}</option>
              <option value="off">{t('linkEmbedsOff')}</option>
            </select>
            {allowedProviders.length > 0 && (
              <div className="flex items-center gap-2">
                <p className="text-xs text-muted-foreground">
                  {t('linkEmbedsAllowed')}: {allowedProviders.join(', ')}
                </p>
                <button onClick={clearAllowed} className="text-xs text-destructive-text hover:underline">
                  {t('linkEmbedsClear')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </SettingsSection>
  );
}
