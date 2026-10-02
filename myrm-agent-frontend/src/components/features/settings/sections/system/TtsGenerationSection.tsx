'use client';

/**
 * [INPUT]
 * - services/config/types::VoiceConfigValue (POS: voice config REST value shape)
 * - lib/api::apiRequest (POS: unified REST entry with auth + locale headers)
 * - lib/utils/media::providerHasActiveApiKey (POS: providers-row credential fallback check)
 * - PremiumIcons (POS: premium glyph set, no native emoji)
 *
 * [OUTPUT]
 * - TtsGenerationSection: Settings panel for the tts_generate agent tool.
 *
 * [POS]
 * TTS tool configuration UI. Provider/model/voice selection plus credential
 * entry. Reads/writes the shared `voice` config (ttsProvider/ttsModel/
 * ttsVoice/ttsApiKey) with optimistic-lock read-modify-write, mirroring the
 * server-side media param extraction chain.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconLoader,
  IconCheckCircle,
  IconXCircle,
  IconAlertCircle,
  IconEye,
  IconEyeOff,
  IconSave,
} from '@/components/features/icons/PremiumIcons';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/shared/useToast';
import { apiRequest } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { providerHasActiveApiKey } from '@/lib/utils/media';
import type { VoiceConfigValue } from '@/services/config/types';
import OptionSelect from '../../OptionSelect';
import SettingsSection from '../SettingsSection';

type TtsProviderId = 'openai' | 'elevenlabs' | 'volcengine';

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

interface TtsModelOption {
  value: string;
  label: string;
  description: string;
}

const TTS_PROVIDER_OPTIONS: TtsModelOption[] = [
  { value: 'openai', label: 'OpenAI TTS', description: 'tts-1 / gpt-4o-mini-tts' },
  { value: 'elevenlabs', label: 'ElevenLabs', description: 'Turbo v2.5 / Multilingual v2' },
  { value: 'volcengine', label: 'Volcengine Speech', description: 'Seed-Audio / Doubao-TTS' },
];

const TTS_MODEL_OPTIONS: Record<TtsProviderId, TtsModelOption[]> = {
  openai: [
    { value: 'tts-1', label: 'TTS 1', description: 'Fast' },
    { value: 'tts-1-hd', label: 'TTS 1 HD', description: 'Higher fidelity' },
    { value: 'gpt-4o-mini-tts', label: 'GPT-4o mini TTS', description: 'Steerable' },
  ],
  elevenlabs: [
    { value: 'eleven_turbo_v2_5', label: 'Turbo v2.5', description: 'Low latency' },
    { value: 'eleven_multilingual_v2', label: 'Multilingual v2', description: '30+ languages' },
    { value: 'eleven_flash_v2_5', label: 'Flash v2.5', description: 'Fastest' },
  ],
  volcengine: [
    { value: 'seed-audio-1.0', label: 'Seed-Audio 1.0', description: 'Generative · style-aware' },
    { value: 'doubao-tts', label: 'Doubao-TTS', description: 'Low latency codec' },
  ],
};

const TTS_VOICE_OPTIONS: Record<TtsProviderId, TtsModelOption[]> = {
  openai: [
    { value: 'alloy', label: 'Alloy', description: '' },
    { value: 'echo', label: 'Echo', description: '' },
    { value: 'fable', label: 'Fable', description: '' },
    { value: 'onyx', label: 'Onyx', description: '' },
    { value: 'nova', label: 'Nova', description: '' },
    { value: 'shimmer', label: 'Shimmer', description: '' },
  ],
  elevenlabs: [
    { value: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel', description: '' },
    { value: 'AZnzlk1XvdvUeBnXmlld', label: 'Domi', description: '' },
    { value: 'EXAVITQu4vr4xnSDxMaL', label: 'Sarah', description: '' },
    { value: 'TxGEqnHWrfWFTfGW9XjX', label: 'Josh', description: '' },
  ],
  volcengine: [
    { value: 'zh_female_vv_uranus_bigtts', label: 'Uranus · 中文女声', description: 'Default' },
    { value: 'zh_male_rough_mars_bigtts', label: 'Mars · 中文男声', description: '' },
    { value: 'en_female_emily_mars_bigtts', label: 'Emily · English', description: '' },
  ],
};

const DEFAULT_PROVIDER: TtsProviderId = 'openai';
const DEFAULT_MODEL = 'tts-1';
const DEFAULT_VOICE = 'alloy';

async function fetchVoiceRecord(): Promise<{ value: VoiceConfigValue; version: string } | null> {
  try {
    const record = await apiRequest<{
      value: VoiceConfigValue;
      meta?: { version?: string };
    }>('/config/voice', { silent: true });
    if (record && typeof record.value === 'object') {
      return { value: record.value, version: record.meta?.version ?? '' };
    }
  } catch {
    /* voice config not created yet — defaults apply */
  }
  return null;
}

async function putVoiceConfig(next: VoiceConfigValue, expectedVersion: string): Promise<void> {
  await apiRequest('/config/voice', {
    method: 'PUT',
    body: JSON.stringify({ value: next, expectedVersion: expectedVersion || undefined }),
    silent: true,
  });
}

async function testTtsConfig(provider: string, model: string): Promise<{ ok: boolean; message: string }> {
  const resp = await fetch(`${getBackendUrl()}/api/v1/agents/test-media-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ mediaType: 'tts', provider, model }),
  });
  const data = await resp.json();
  if (data.success || data.data?.status === 'ok') {
    return { ok: true, message: data.data?.message ?? 'OK' };
  }
  return { ok: false, message: data.message ?? 'Test failed' };
}

const TtsGenerationSection = memo(() => {
  const t = useTranslations('settings.mediaGeneration');

  const providers = useProviderStore((s) => s.providers);

  const [ttsProvider, setTtsProvider] = useState<TtsProviderId>(DEFAULT_PROVIDER);
  const [ttsModel, setTtsModel] = useState<string>(DEFAULT_MODEL);
  const [ttsVoice, setTtsVoice] = useState<string>(DEFAULT_VOICE);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [keyConfigured, setKeyConfigured] = useState<boolean | null>(null);
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [voiceVersion, setVoiceVersion] = useState('');

  useEffect(() => {
    let cancelled = false;
    void fetchVoiceRecord().then((record) => {
      if (cancelled || !record) {
        return;
      }
      const value = record.value;
      const provider = (value.ttsProvider as TtsProviderId) || DEFAULT_PROVIDER;
      const model = value.ttsModel || DEFAULT_MODEL;
      setVoiceVersion(record.version);
      if (provider === 'volcengine' && model === 'tts-1') {
        setTtsModel('seed-audio-1.0');
      } else if (provider === 'elevenlabs' && model === 'tts-1') {
        setTtsModel('eleven_turbo_v2_5');
      } else {
        setTtsModel(model);
      }
      setTtsProvider(provider);
      setTtsVoice(value.ttsVoice || DEFAULT_VOICE);
      setKeyConfigured(Boolean(value.ttsApiKey?.trim()) || providerHasActiveApiKey(providers, provider));
    });
    return () => {
      cancelled = true;
    };
  }, [providers]);

  const handleProviderChange = useCallback((next: string) => {
    const p = next as TtsProviderId;
    setTtsProvider(p);
    setTtsModel(TTS_MODEL_OPTIONS[p][0].value);
    setTtsVoice(TTS_VOICE_OPTIONS[p][0].value);
  }, []);

  const handleModelChange = useCallback((model: string) => {
    setTtsModel(model);
  }, []);

  const handleVoiceChange = useCallback((voice: string) => {
    setTtsVoice(voice);
  }, []);

  const handleSaveApiKey = useCallback(async () => {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      return;
    }
    setSavingKey(true);
    try {
      const record = await fetchVoiceRecord();
      const base: VoiceConfigValue =
        record?.value ??
        ({
          sttEnabled: false,
          sttProvider: 'openai',
          sttApiKey: '',
          sttModel: 'whisper-1',
          sttLanguage: '',
          sttLocalModel: 'base',
          sttLocalDevice: 'auto',
          sttLocalComputeType: 'auto',
          sttBaseUrl: '',
          ttsMode: 'off',
          ttsProvider: DEFAULT_PROVIDER,
          ttsApiKey: '',
          ttsBaseUrl: '',
          ttsVoice: DEFAULT_VOICE,
          ttsMaxLength: 4000,
          ttsSummaryEnabled: true,
          ttsSummaryThreshold: 1500,
          ttsSummaryModel: '',
        } satisfies VoiceConfigValue);
      const next: VoiceConfigValue = {
        ...base,
        ttsProvider,
        ttsModel,
        ttsVoice,
        ttsApiKey: trimmed,
      };
      await putVoiceConfig(next, record?.version ?? voiceVersion);
      setKeyConfigured(true);
      setApiKey('');
      toast.success(t('apiKeySaved') || 'API Key saved successfully!');
    } catch (error) {
      console.error('Failed to save TTS API Key:', error);
      toast.error(t('apiKeySaveFailed') || 'Failed to save API Key');
    } finally {
      setSavingKey(false);
    }
  }, [ttsProvider, ttsModel, ttsVoice, apiKey, voiceVersion, t]);

  const handleTest = useCallback(async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testTtsConfig(ttsProvider, ttsModel);
      setTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) {
        setTestMessage(result.message);
      }
    } catch {
      setTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setTestStatus('idle'), 3000);
  }, [ttsProvider, ttsModel]);

  const isDoubao = ttsProvider === 'volcengine' && ttsModel === 'doubao-tts';
  const keyPlaceholder = isDoubao ? 'appid:access_token' : t('enterApiKey') || 'Enter API Key';

  return (
    <SettingsSection title={t('ttsTitle')} description={t('ttsDescription')}>
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">{t('ttsProvider')}</label>
            {keyConfigured === true && (
              <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <IconCheckCircle className="h-3 w-3" />
                {t('configured')}
              </span>
            )}
            {keyConfigured === false && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                <IconAlertCircle className="h-3 w-3" />
                {t('needsApiKey')}
              </span>
            )}
          </div>
          <OptionSelect
            value={ttsProvider}
            options={TTS_PROVIDER_OPTIONS}
            onChange={handleProviderChange}
            hideDescription={false}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('ttsModel')}</label>
          <OptionSelect
            value={ttsModel}
            options={TTS_MODEL_OPTIONS[ttsProvider]}
            onChange={handleModelChange}
            hideDescription={false}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('ttsVoice')}</label>
          <OptionSelect
            value={ttsVoice}
            options={TTS_VOICE_OPTIONS[ttsProvider]}
            onChange={handleVoiceChange}
            hideDescription={false}
          />
        </div>

        {keyConfigured !== true && (
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
            <p className="text-xs text-amber-700 dark:text-amber-400">
              {isDoubao
                ? t('ttsDoubaoKeyHint') || 'Doubao-TTS uses the composite credential "appid:access_token".'
                : t('apiKeyHint') ||
                    'Please configure the API Key for this provider. The key will be shared globally across all features.'}
            </p>
            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground">{t('apiKey') || 'API Key'}</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={keyPlaceholder}
                    className="w-full rounded-full border border-border bg-background px-3 py-1.5 pr-10 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showApiKey ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={handleSaveApiKey}
                  disabled={!apiKey.trim() || savingKey}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                >
                  {savingKey ? <IconLoader className="h-3 w-3 animate-spin" /> : <IconSave className="h-3 w-3" />}
                  {t('save') || 'Save'}
                </button>
              </div>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={handleTest}
          disabled={testStatus === 'testing'}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
        >
          {testStatus === 'testing' && <IconLoader className="h-3 w-3 animate-spin" />}
          {testStatus === 'success' && <IconCheckCircle className="h-3 w-3 text-green-500" />}
          {testStatus === 'error' && <IconXCircle className="h-3 w-3 text-red-500" />}
          {t('testConnection')}
        </button>
        {testStatus === 'error' && testMessage && <p className="text-xs text-red-500">{testMessage}</p>}
      </div>
    </SettingsSection>
  );
});

TtsGenerationSection.displayName = 'TtsGenerationSection';

export default TtsGenerationSection;
