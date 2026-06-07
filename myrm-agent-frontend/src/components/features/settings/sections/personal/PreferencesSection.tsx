'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import {
  Sorting01Icon,
  Mic01Icon,
  Video01Icon,
  TextFontIcon,
  BulbIcon,
  File01Icon,
  Coins01Icon,
  CircleIcon,
  Wifi01Icon,
  VoiceIcon,
  ArrowDataTransferHorizontalIcon,
} from 'hugeicons-react';
import { IconAlertCircle, IconFlask } from '@/components/features/icons/PremiumIcons';
import useConfigStore from '@/store/useConfigStore';
import useRetrievalStore from '@/store/useRetrievalStore';
import { toast } from '@/lib/utils/toast';
import ThemeSwitcher from '../../Switcher';
import SkinPicker from '../../SkinPicker';
import LanguageSwitcher from '../../LanguageSwitcher';
import ConfigToggleItem from '../../ConfigToggleItem';
import SettingsSection from '../SettingsSection';
import NotificationChannelEditor from '../integration/channels/NotificationChannelEditor';
import { SchemaForm } from '../../SchemaForm';
import { ConfigTimeMachine } from '../../ConfigTimeMachine';
import { usePersonalSettings } from '@/hooks/usePersonalSettings';
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

const VOICE_SESSION_KEY = 'voiceSessionEnabled';
const VOICE_CAMERA_KEY = 'voiceCameraEnabled';
const VOICE_FULL_DUPLEX_KEY = 'voiceFullDuplexEnabled';
const VOICE_AGENT_BRIDGE_KEY = 'voiceAgentBridgeEnabled';

const PreferencesSection = memo(() => {
  const t = useTranslations('settings');
  const tRetrieval = useTranslations('settings.retrieval');
  const tVoice = useTranslations('voiceSession');
  const { initConfig } = useConfigStore();
  const { personalSettings, updatePersonalSettings } = usePersonalSettings();
  const isLocal = isLocalMode();
  const schemaVisibilityContext = { isLocal, value: personalSettings as Record<string, unknown> };

  const { enableAdvancedRetrieval, setEnableAdvancedRetrieval, embeddingApplied, rerankerApplied } =
    useRetrievalStore();

  const [isLoading, setIsLoading] = useState(true);

  const [voiceSessionEnabled, setVoiceSessionEnabled] = useState(() =>
    typeof window !== 'undefined' ? localStorage.getItem(VOICE_SESSION_KEY) === 'true' : false,
  );
  const [voiceCameraEnabled, setVoiceCameraEnabled] = useState(() =>
    typeof window !== 'undefined' ? localStorage.getItem(VOICE_CAMERA_KEY) === 'true' : false,
  );
  const [voiceFullDuplexEnabled, setVoiceFullDuplexEnabled] = useState(() =>
    typeof window !== 'undefined' ? localStorage.getItem(VOICE_FULL_DUPLEX_KEY) !== 'false' : true,
  );
  const [voiceAgentBridgeEnabled, setVoiceAgentBridgeEnabled] = useState(() =>
    typeof window !== 'undefined' ? localStorage.getItem(VOICE_AGENT_BRIDGE_KEY) === 'true' : false,
  );

  const handleVoiceSessionToggle = useCallback((checked: boolean) => {
    setVoiceSessionEnabled(checked);
    localStorage.setItem(VOICE_SESSION_KEY, String(checked));
  }, []);

  const handleVoiceCameraToggle = useCallback((checked: boolean) => {
    setVoiceCameraEnabled(checked);
    localStorage.setItem(VOICE_CAMERA_KEY, String(checked));
  }, []);

  const handleVoiceFullDuplexToggle = useCallback((checked: boolean) => {
    setVoiceFullDuplexEnabled(checked);
    localStorage.setItem(VOICE_FULL_DUPLEX_KEY, String(checked));
  }, []);

  const handleVoiceAgentBridgeToggle = useCallback((checked: boolean) => {
    setVoiceAgentBridgeEnabled(checked);
    localStorage.setItem(VOICE_AGENT_BRIDGE_KEY, String(checked));
  }, []);

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
    enableEvalLab: IconFlask,
    webTtsProvider: VoiceIcon,
    enableCompletionSound: VoiceIcon,
    enableWebNotifications: IconAlertCircle,
  };

  useEffect(() => {
    if (enableAdvancedRetrieval && (!embeddingApplied || !rerankerApplied)) {
      setEnableAdvancedRetrieval(false);
    }
  }, [embeddingApplied, rerankerApplied, enableAdvancedRetrieval, setEnableAdvancedRetrieval]);

  const handleAdvancedRetrievalChange = useCallback(
    (checked: boolean) => {
      if (checked && (!embeddingApplied || !rerankerApplied)) {
        toast.warning(tRetrieval('advancedRetrieval.cannotEnable'));
        return;
      }
      setEnableAdvancedRetrieval(checked);
    },
    [embeddingApplied, rerankerApplied, setEnableAdvancedRetrieval, tRetrieval],
  );

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
          <SkinPicker />
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

      <SettingsSection title={tVoice('enableVoiceSession')}>
        <div className="flex flex-col space-y-4">
          <ConfigToggleItem
            icon={Mic01Icon}
            title={tVoice('enableVoiceSession')}
            description={tVoice('enableVoiceSessionDesc')}
            checked={voiceSessionEnabled}
            onCheckedChange={handleVoiceSessionToggle}
          />
          <ConfigToggleItem
            icon={ArrowDataTransferHorizontalIcon}
            title={tVoice('fullDuplex')}
            description={tVoice('fullDuplexDesc')}
            checked={voiceFullDuplexEnabled}
            onCheckedChange={handleVoiceFullDuplexToggle}
          />
          <ConfigToggleItem
            icon={Video01Icon}
            title={tVoice('enableCamera')}
            description={tVoice('enableCameraDesc')}
            checked={voiceCameraEnabled}
            onCheckedChange={handleVoiceCameraToggle}
          />
          <ConfigToggleItem
            icon={Wifi01Icon}
            title={tVoice('agentBridge')}
            description={tVoice('agentBridgeDesc')}
            checked={voiceAgentBridgeEnabled}
            onCheckedChange={handleVoiceAgentBridgeToggle}
          />
        </div>
      </SettingsSection>

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
        </div>
      </SettingsSection>

      <SettingsSection title={tRetrieval('advancedRetrieval.title')}>
        <div className="flex flex-col space-y-4">
          <ConfigToggleItem
            icon={Sorting01Icon}
            title={tRetrieval('advancedRetrieval.toggleLabel')}
            description={tRetrieval('advancedRetrieval.toggleDescription')}
            checked={enableAdvancedRetrieval}
            onCheckedChange={handleAdvancedRetrievalChange}
          />
        </div>
      </SettingsSection>
    </div>
  );
});

PreferencesSection.displayName = 'PreferencesSection';

export default PreferencesSection;
