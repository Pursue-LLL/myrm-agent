'use client';

import { memo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { TextFontIcon, BulbIcon, File01Icon, Coins01Icon, CircleIcon, Wifi01Icon, VoiceIcon } from 'hugeicons-react';
import { IconAlertCircle, IconFlask } from '@/components/features/icons/PremiumIcons';
import useConfigStore from '@/store/useConfigStore';
import useEmbedConsentStore, { type EmbedMode } from '@/store/useEmbedConsentStore';
import ThemeSwitcher from '../../Switcher';
import AppearancePanel from '@/components/features/theme/AppearancePanel';
import LanguageSwitcher from '../../LanguageSwitcher';
import SettingsSection from '../SettingsSection';
import NotificationChannelEditor from '../integration/channels/NotificationChannelEditor';
import WebPushCard from './WebPushCard';
import VoiceSessionToggles from './VoiceSessionToggles';
import { SchemaForm } from '../../SchemaForm';
import { ConfigTimeMachine } from '../../ConfigTimeMachine';
import { usePersonalSettings } from '@/hooks/settings/usePersonalSettings';
import OptionSelect from '../../OptionSelect';
import { isLocalMode } from '@/lib/deploy-mode';
import type { WebTtsProvider } from '@/services/config/types';

const WEB_TTS_OPTIONS: Array<{ value: WebTtsProvider; labelKey: string; descKey: string }> = [
  { value: 'browser', labelKey: 'webTts.browser', descKey: 'webTts.browserDesc' },
  { value: 'openai', labelKey: 'webTts.openai', descKey: 'webTts.openaiDesc' },
  { value: 'elevenlabs', labelKey: 'webTts.elevenlabs', descKey: 'webTts.elevenlabsDesc' },
  { value: 'fish_audio', labelKey: 'webTts.fishAudio', descKey: 'webTts.fishAudioDesc' },
  { value: 'minimax', labelKey: 'webTts.minimax', descKey: 'webTts.minimaxDesc' },
  { value: 'edge', labelKey: 'webTts.edge', descKey: 'webTts.edgeDesc' },
];

const PreferencesSection = memo(() => {
  const t = useTranslations('settings');
  const { initConfig } = useConfigStore();
  const { personalSettings, updatePersonalSettings } = usePersonalSettings();
  const isLocal = isLocalMode();
  const schemaVisibilityContext = {
    isLocal,
    value: personalSettings as unknown as Record<string, unknown>,
  };

  const embedMode = useEmbedConsentStore((s) => s.embedMode);
  const setEmbedMode = useEmbedConsentStore((s) => s.setEmbedMode);
  const allowedProviders = useEmbedConsentStore((s) => s.allowedProviders);
  const clearAllowed = useEmbedConsentStore((s) => s.clearAllowed);

  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    initConfig();
    setIsLoading(false);
  }, [initConfig]);

  const personalSettingsIconMap = {
    enableAutoTitleGeneration: TextFontIcon,
    generateSearchSuggestions: BulbIcon,
    fetchRawWebpage: File01Icon,
    extractDocumentText: File01Icon,
    enableCostEstimation: Coins01Icon,
    enableCacheBreakNotification: IconAlertCircle,
    showContextUsage: CircleIcon,
    codeExecutionAllowNetwork: Wifi01Icon,
    enterpriseTlsCompat: Wifi01Icon,
    enableEvalLab: IconFlask,
    webTtsProvider: VoiceIcon,
    enableCompletionSound: VoiceIcon,
    enableWebNotifications: IconAlertCircle,
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between py-3">
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-8 w-12 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SettingsSection title={t('appearance')}>
        <div className="flex flex-col space-y-4">
          <ThemeSwitcher />
          <AppearancePanel />
        </div>
      </SettingsSection>

      <SettingsSection title={t('linkEmbeds')}>
        <div className="flex flex-col space-y-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 shrink-0 rounded-lg bg-primary/10 p-2 text-primary">
              <BulbIcon size={18} />
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <div>
                <p className="text-sm font-medium text-foreground">{t('linkEmbedsMode')}</p>
                <p className="text-xs text-muted-foreground">{t('linkEmbedsDesc')}</p>
              </div>
              <select
                value={embedMode}
                onChange={(e) => setEmbedMode(e.target.value as EmbedMode)}
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

      <SettingsSection title={t('language')}>
        <div className="flex flex-col space-y-3">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-primary/10 text-primary shrink-0 mt-0.5">
              <TextFontIcon size={18} />
            </div>
            <div className="flex-1 min-w-0 space-y-2">
              <div>
                <p className="text-sm font-medium text-foreground">{t('language')}</p>
                <p className="text-xs text-muted-foreground">{t('languageChannelSyncDesc')}</p>
              </div>
              <LanguageSwitcher />
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title={t('webTts.sectionTitle')}>
        <div className="flex flex-col space-y-3">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 shrink-0 rounded-lg bg-primary/10 p-2 text-primary">
              <VoiceIcon size={18} />
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <div>
                <p className="text-sm font-medium text-foreground">{t('webTts.providerLabel')}</p>
                <p className="text-xs text-muted-foreground">{t('webTts.providerDesc')}</p>
              </div>
              <OptionSelect<WebTtsProvider>
                value={personalSettings.webTtsProvider}
                options={WEB_TTS_OPTIONS.map((opt) => ({
                  value: opt.value,
                  label: t(opt.labelKey),
                  description: t(opt.descKey),
                }))}
                onChange={(provider) => updatePersonalSettings({ webTtsProvider: provider })}
              />
            </div>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('personalSettingsTitle')}
        description={t('personalSettingsDesc')}
        action={<ConfigTimeMachine configKey="personalSettings" onRestore={updatePersonalSettings} />}
      >
        <div className="p-4 bg-secondary/20 rounded-xl border border-border/40">
          <SchemaForm
            configKey="personalSettings"
            value={personalSettings}
            onChange={updatePersonalSettings}
            iconMap={personalSettingsIconMap}
            section="preferences"
            group="basic"
            visibilityContext={schemaVisibilityContext}
          />
        </div>
      </SettingsSection>

      <SettingsSection title={t('advancedSettings')}>
        <div className="p-4 bg-secondary/20 rounded-xl border border-border/40">
          <SchemaForm
            configKey="personalSettings"
            value={personalSettings}
            onChange={updatePersonalSettings}
            iconMap={personalSettingsIconMap}
            section="preferences"
            group="advanced"
            visibilityContext={schemaVisibilityContext}
          />
        </div>
      </SettingsSection>

      <VoiceSessionToggles />

      <SettingsSection title={t('notifications')}>
        <div className="flex flex-col space-y-4">
          <div className="rounded-xl border border-border/40 bg-secondary/20 p-4">
            <SchemaForm
              configKey="personalSettings"
              value={personalSettings}
              onChange={updatePersonalSettings}
              iconMap={personalSettingsIconMap}
              section="notifications"
            />
          </div>
          <NotificationChannelEditor />
          <WebPushCard />
        </div>
      </SettingsSection>
    </div>
  );
});

PreferencesSection.displayName = 'PreferencesSection';

export default PreferencesSection;
