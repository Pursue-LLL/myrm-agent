'use client';

/**
 * [INPUT]
 * - lib/utils/media (POS: TTS catalog, stored-choice mapping, providers-row credential fallback check)
 * - lib/api::apiRequest (POS: unified REST entry with auth + locale headers)
 * - ./MediaSettingsParts (POS: key badge, key form, empty-dropdown prompt)
 * - app-shell/config-load-error::ConfigLoadError (POS: failed-read view with retry)
 * - primitives/skeleton::Skeleton (POS: loading placeholder)
 *
 * [OUTPUT]
 * - TtsGenerationSection: Settings panel for the tts_generate agent tool.
 *
 * [POS]
 * TTS tool configuration UI. Provider/model/voice selection plus credential entry. Reads/writes the shared `voice`
 * config (ttsProvider/ttsModel/ttsVoice/ttsApiKey) with optimistic-lock read-modify-write, mirroring the server-side
 * media param extraction chain. Nothing is chosen for the user: with no stored choice the dropdowns ask for one, and
 * every choice is saved as soon as it is made, because the agent gets the tool only from a saved provider, model and
 * voice. Changing the provider replaces the model and voice with that provider's first ones and drops the stored key,
 * which belonged to the previous provider. The card is offered only once the stored settings have been read, and each
 * write re-reads them first: a read that fails never turns into a write, so the other voice settings are never
 * replaced by defaults. The channel voice settings share these fields, so a stored provider this card does not offer
 * counts as nothing chosen here.
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { IconCheckCircle, IconLoader, IconXCircle } from '@/components/features/icons/PremiumIcons';
import { Skeleton } from '@/components/primitives/skeleton';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/shared/useToast';
import { apiRequest } from '@/lib/api';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import {
  isTtsProvider,
  providerHasActiveApiKey,
  readStoredChoices,
  TTS_MODEL_OPTIONS,
  TTS_PROVIDER_OPTIONS,
  TTS_VOICE_OPTIONS,
  type StoredVoice,
  type TtsProviderId,
} from '@/lib/utils/media';
import OptionSelect from '../../OptionSelect';
import SettingsSection from '../SettingsSection';
import { KeyStatusBadge, MediaApiKeyForm, selectionPlaceholderKey } from './MediaSettingsParts';

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

type LoadStatus = 'loading' | 'ready' | 'failed';

/** What the card shows as chosen; an empty string is nothing chosen. */
interface Choices {
  provider: string;
  model: string;
  voice: string;
}

const NOTHING_CHOSEN: Choices = { provider: '', model: '', voice: '' };

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

/** Writes the choices (and any other fields given) into what is stored now, keeping every other voice setting. */
async function saveVoiceFields(fields: StoredVoice): Promise<void> {
  const record = await fetchVoiceRecord();
  await putVoiceConfig({ ...record.value, ...fields }, record.version);
}

const choiceFields = (choices: Choices): StoredVoice => ({
  ttsProvider: choices.provider,
  ttsModel: choices.model,
  ttsVoice: choices.voice,
});

async function testTtsConfig(choices: Choices): Promise<{ ok: boolean; message: string }> {
  const resp = await fetch(`${getBackendUrl()}/api/v1/agents/test-media-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({
      mediaType: 'tts',
      provider: choices.provider,
      model: choices.model,
      voice: choices.voice,
    }),
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

  const [choices, setChoices] = useState<Choices>(NOTHING_CHOSEN);
  const [apiKey, setApiKey] = useState('');
  const [savingKey, setSavingKey] = useState(false);
  const [keyConfigured, setKeyConfigured] = useState(false);
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [loadStatus, setLoadStatus] = useState<LoadStatus>('loading');
  const [reloads, setReloads] = useState(0);
  // Choices are written one after another, so quick successive changes never overwrite each other.
  const writes = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let cancelled = false;
    // A read waits for the choices still being written, so it never brings back an older answer.
    writes.current.then(fetchVoiceRecord).then(
      ({ value }) => {
        if (cancelled) {
          return;
        }
        const stored = readStoredChoices(value);
        setChoices({ provider: stored.provider, model: stored.model, voice: stored.voice });
        setKeyConfigured(
          stored.keySaved || (isTtsProvider(stored.provider) && providerHasActiveApiKey(providers, stored.provider)),
        );
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

  /** Shows the choices now and saves them; a save that fails brings back what is really stored. */
  const choose = useCallback(
    (next: Choices, otherFields: StoredVoice = {}) => {
      setChoices(next);
      writes.current = writes.current
        .then(() => saveVoiceFields({ ...choiceFields(next), ...otherFields }))
        .catch((error: unknown) => {
          console.error('Failed to save TTS selection:', error);
          toast.error(t('ttsSelectionSaveFailed'));
          setReloads((count) => count + 1);
        });
    },
    [t],
  );

  const handleProviderChange = useCallback(
    (next: string) => {
      if (!isTtsProvider(next) || next === choices.provider) {
        return;
      }
      choose(
        { provider: next, model: TTS_MODEL_OPTIONS[next][0].value, voice: TTS_VOICE_OPTIONS[next][0].value },
        { ttsApiKey: '' },
      );
      setKeyConfigured(providerHasActiveApiKey(providers, next));
    },
    [choices.provider, choose, providers],
  );

  const handleModelChange = useCallback((model: string) => choose({ ...choices, model }), [choices, choose]);

  const handleVoiceChange = useCallback((voice: string) => choose({ ...choices, voice }), [choices, choose]);

  const handleSaveApiKey = useCallback(async () => {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      return;
    }
    setSavingKey(true);
    try {
      // The write merges into what is stored now. A read that fails ends the save here: writing without it would
      // replace the other voice settings with whatever this card knows.
      await writes.current;
      await saveVoiceFields({ ...choiceFields(choices), ttsApiKey: trimmed });
      setKeyConfigured(true);
      setApiKey('');
      toast.success(t('apiKeySaved'));
    } catch (error) {
      console.error('Failed to save TTS API Key:', error);
      toast.error(t('apiKeySaveFailed'));
    } finally {
      setSavingKey(false);
    }
  }, [choices, apiKey, t]);

  const handleTest = useCallback(async () => {
    setTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testTtsConfig(choices);
      setTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) {
        setTestMessage(result.message);
      }
    } catch {
      setTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setTestStatus('idle'), 3000);
  }, [choices]);

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

  const provider: TtsProviderId | undefined = isTtsProvider(choices.provider) ? choices.provider : undefined;
  const modelOptions = provider ? TTS_MODEL_OPTIONS[provider] : [];
  const voiceOptions = provider ? TTS_VOICE_OPTIONS[provider] : [];
  const isDoubao = provider === 'volcengine' && choices.model === 'doubao-tts';
  const isSeedAudio = provider === 'volcengine' && choices.model === 'seed-audio-1.0';

  return (
    <SettingsSection title={t('ttsTitle')} description={t('ttsDescription')}>
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">{t('ttsProvider')}</label>
            {provider && <KeyStatusBadge status={keyConfigured ? 'configured' : 'needsKey'} t={t} />}
          </div>
          <OptionSelect
            value={choices.provider}
            options={TTS_PROVIDER_OPTIONS}
            onChange={handleProviderChange}
            placeholder={t(selectionPlaceholderKey(choices.provider, TTS_PROVIDER_OPTIONS))}
            hideDescription={false}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('ttsModel')}</label>
          <OptionSelect
            value={choices.model}
            options={modelOptions}
            onChange={handleModelChange}
            placeholder={t(provider ? selectionPlaceholderKey(choices.model, modelOptions) : 'selectPlaceholder')}
            disabled={!provider}
            hideDescription={false}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('ttsVoice')}</label>
          <OptionSelect
            value={choices.voice}
            options={voiceOptions}
            onChange={handleVoiceChange}
            placeholder={t(provider ? selectionPlaceholderKey(choices.voice, voiceOptions) : 'selectPlaceholder')}
            disabled={!provider}
            hideDescription={false}
          />
        </div>

        {provider && !keyConfigured && (
          <MediaApiKeyForm
            hint={isDoubao ? t('ttsDoubaoKeyHint') : t('apiKeyHint')}
            label={t('apiKey')}
            placeholder={isDoubao ? 'appid:access_token' : t('enterApiKey')}
            saveLabel={t('save')}
            value={apiKey}
            onChange={setApiKey}
            onSave={handleSaveApiKey}
            saving={savingKey}
          />
        )}

        {isSeedAudio && <p className="text-xs text-amber-600 dark:text-amber-400">{t('ttsProbeSlowHint')}</p>}
        <button
          type="button"
          onClick={handleTest}
          disabled={!provider || testStatus === 'testing'}
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
