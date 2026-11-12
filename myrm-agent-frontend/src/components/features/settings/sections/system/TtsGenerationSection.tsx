'use client';

/**
 * [INPUT]
 * - ./ttsCatalog (POS: provider/model/voice options and the mapping of stored voice settings onto them)
 * - lib/api::apiRequest (POS: unified REST entry with auth + locale headers)
 * - lib/utils/media::providerHasActiveApiKey (POS: providers-row credential fallback check)
 * - app-shell/config-load-error::ConfigLoadError (POS: failed-read view with retry)
 * - primitives/skeleton::Skeleton (POS: loading placeholder)
 * - PremiumIcons (POS: premium glyph set, no native emoji)
 *
 * [OUTPUT]
 * - TtsGenerationSection: Settings panel for the tts_generate agent tool.
 *
 * [POS]
 * TTS tool configuration UI. Provider/model/voice selection plus credential
 * entry. Reads/writes the shared `voice` config (ttsProvider/ttsModel/
 * ttsVoice/ttsApiKey) with optimistic-lock read-modify-write, mirroring the
 * server-side media param extraction chain. The card is offered only once the
 * stored settings have been read, and a save re-reads them first: a read that
 * fails never turns into a write, so the other voice settings are never
 * replaced by defaults. The channel voice settings share these fields, so a
 * stored provider this card does not offer shows the card's own defaults.
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
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { Skeleton } from '@/components/primitives/skeleton';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/shared/useToast';
import { apiRequest } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { providerHasActiveApiKey } from '@/lib/utils/media';
import OptionSelect from '../../OptionSelect';
import SettingsSection from '../SettingsSection';
import {
  DEFAULT_MODEL,
  DEFAULT_PROVIDER,
  DEFAULT_VOICE,
  readStoredChoices,
  TTS_MODEL_OPTIONS,
  TTS_PROVIDER_OPTIONS,
  TTS_VOICE_OPTIONS,
  type StoredVoice,
  type TtsProviderId,
} from './ttsCatalog';

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

type LoadStatus = 'loading' | 'ready' | 'failed';

/**
 * Rejects when the stored settings cannot be read, so a failed read is never taken for "nothing saved yet": that case
 * is not a failure, the server answers it with an empty value. The read is silent because the card shows the failure
 * itself, with a retry that reaches the card.
 */
async function fetchVoiceRecord(): Promise<{ value: StoredVoice; version: string }> {
  const record = await apiRequest<{ value?: StoredVoice | null; meta?: { version?: string } }>('/config/voice', {
    silent: true,
  });
  if (typeof record?.value !== 'object' || record.value === null) {
    throw new Error('The voice settings answer carries no value');
  }
  return { value: record.value, version: record.meta?.version ?? '' };
}

/** Every config write names its device; the channel voice settings, which write this same key, send 'web' too. */
async function putVoiceConfig(next: StoredVoice, expectedVersion: string): Promise<void> {
  await apiRequest('/config/voice', {
    method: 'PUT',
    body: JSON.stringify({ value: next, expectedVersion: expectedVersion || undefined, deviceId: 'web' }),
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
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [loadStatus, setLoadStatus] = useState<LoadStatus>('loading');
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchVoiceRecord().then(
      ({ value }) => {
        if (cancelled) {
          return;
        }
        const choices = readStoredChoices(value);
        setTtsProvider(choices.provider);
        setTtsModel(choices.model);
        setTtsVoice(choices.voice);
        setKeyConfigured(choices.keySaved || providerHasActiveApiKey(providers, choices.provider));
        setLoadStatus('ready');
      },
      () => {
        // Only a first read has nothing to fall back on; a later one that fails leaves what is shown.
        if (!cancelled) {
          setLoadStatus((current) => (current === 'ready' ? current : 'failed'));
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [providers, reloads]);

  const retryLoad = useCallback(() => {
    setLoadStatus('loading');
    setReloads((count) => count + 1);
  }, []);

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
      // The write merges into what is stored now. A read that fails ends the save here: writing without it would
      // replace the other voice settings with whatever this card knows. Settings not saved yet read as an empty
      // value, and the server fills in the rest.
      const record = await fetchVoiceRecord();
      await putVoiceConfig({ ...record.value, ttsProvider, ttsModel, ttsVoice, ttsApiKey: trimmed }, record.version);
      setKeyConfigured(true);
      setApiKey('');
      toast.success(t('apiKeySaved'));
    } catch (error) {
      console.error('Failed to save TTS API Key:', error);
      toast.error(t('apiKeySaveFailed'));
    } finally {
      setSavingKey(false);
    }
  }, [ttsProvider, ttsModel, ttsVoice, apiKey, t]);

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

  if (loadStatus !== 'ready') {
    return (
      <SettingsSection title={t('ttsTitle')} description={t('ttsDescription')}>
        {loadStatus === 'loading' ? (
          <div className="space-y-4">
            <Skeleton className="h-10 w-full rounded-lg" />
            <Skeleton className="h-10 w-full rounded-lg" />
            <Skeleton className="h-10 w-full rounded-lg" />
          </div>
        ) : (
          <ConfigLoadError onRetry={retryLoad} className="py-6" />
        )}
      </SettingsSection>
    );
  }

  const isDoubao = ttsProvider === 'volcengine' && ttsModel === 'doubao-tts';
  const isSeedAudio = ttsProvider === 'volcengine' && ttsModel === 'seed-audio-1.0';
  const keyPlaceholder = isDoubao ? 'appid:access_token' : t('enterApiKey');

  return (
    <SettingsSection title={t('ttsTitle')} description={t('ttsDescription')}>
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">{t('ttsProvider')}</label>
            {keyConfigured ? (
              <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <IconCheckCircle className="h-3 w-3" />
                {t('configured')}
              </span>
            ) : (
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

        {!keyConfigured && (
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
            <p className="text-xs text-amber-700 dark:text-amber-400">
              {isDoubao ? t('ttsDoubaoKeyHint') : t('apiKeyHint')}
            </p>
            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground">{t('apiKey')}</label>
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
                  {t('save')}
                </button>
              </div>
            </div>
          </div>
        )}

        {isSeedAudio && <p className="text-xs text-amber-600 dark:text-amber-400">{t('ttsProbeSlowHint')}</p>}
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
