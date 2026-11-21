'use client';

/**
 * [INPUT]
 * - lib/utils/media (POS: image model catalog, provider-table ids, provider status, key detection)
 * - store/useConfigStore (POS: stored image / video selections, synced to the server)
 * - store/useProviderStore (POS: provider rows and their keys)
 * - ./MediaSettingsParts (POS: key badge, key form, empty-dropdown prompt)
 * - ./TtsGenerationSection (POS: speech card)
 *
 * [OUTPUT]
 * - MediaGenerationSection: Settings panel for the image, video and speech tools of the agent.
 *
 * [POS]
 * Media tool configuration. Nothing is chosen for the user: with no stored choice, or one the catalog no longer
 * offers (for example a model its vendor has retired), the dropdowns ask for a choice, and the agent gets the tool
 * only once the user has made it.
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import { IconLoader, IconCheckCircle, IconXCircle } from '@/components/features/icons/PremiumIcons';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/shared/useToast';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ImageGenerationConfig, VideoGenerationConfig, VideoGenerationProvider } from '@/services/config/types';
import {
  fetchMediaProviderStatus,
  IMAGE_MODEL_OPTIONS,
  isImageModelSelected,
  providerHasActiveApiKey,
  resolveImageProviderId,
  videoProviderConfigId,
  type MediaProviderStatus,
} from '@/lib/utils/media';
import OptionSelect from '../../OptionSelect';
import SettingsSection from '../SettingsSection';
import { KeyStatusBadge, MediaApiKeyForm, selectionPlaceholderKey, type KeyStatus } from './MediaSettingsParts';
import TtsGenerationSection from './TtsGenerationSection';

/** Shown while the server's provider list is not available. */
const FALLBACK_VIDEO_PROVIDERS: {
  value: VideoGenerationProvider;
  label: string;
  description: string;
}[] = [
  { value: 'gemini', label: 'Google Veo', description: 'veo-3.1-fast-generate-preview' },
  { value: 'qwen', label: 'Qwen Wan', description: 'wan2.6-t2v' },
  { value: 'minimax', label: 'MiniMax Hailuo', description: 'MiniMax-Hailuo-2.3' },
  { value: 'xai', label: 'xAI Grok', description: 'grok-imagine-video' },
  { value: 'fal', label: 'FAL.ai', description: 'fal-ai/flux-3-video & Kling' },
  { value: 'volcengine', label: 'Volcengine Seedance', description: 'seedance-2-0' },
];

/** The stored image settings with another model; settings the app no longer keeps are not carried along. */
function withImageModel(current: ImageGenerationConfig | undefined, model: string): ImageGenerationConfig {
  return {
    model,
    fallbackModels: current?.fallbackModels ?? [],
    defaultSize: current?.defaultSize ?? '1024x1024',
    timeoutSeconds: current?.timeoutSeconds ?? 120,
    maxRetries: current?.maxRetries ?? 1,
  };
}

/** The settings of a video selection that are not the selection itself. */
const VIDEO_CONFIG_BASE = {
  fallbackProviders: [],
  timeoutSeconds: 300,
  maxRetries: 1,
} satisfies Omit<VideoGenerationConfig, 'provider' | 'model'>;

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

async function testMediaConfig(
  mediaType: 'image' | 'video',
  provider: string,
  model: string,
): Promise<{ ok: boolean; message: string }> {
  const resp = await fetch(`${getBackendUrl()}/api/v1/agents/test-media-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ mediaType, provider, model }),
  });
  const data = await resp.json();
  if (data.success || data.data?.status === 'ok') {
    return { ok: true, message: data.data?.message ?? 'OK' };
  }
  return { ok: false, message: data.message ?? 'Test failed' };
}

/** Resolves once the settings are on the backend: a change that could only be kept for a later retry is not a save. */
async function syncSettings(): Promise<void> {
  const { success, error } = await getConfigSyncManager().forceSync();
  if (!success) {
    throw new Error(error ?? 'The settings did not reach the backend');
  }
}

function videoKeyStatus(status: MediaProviderStatus | undefined): KeyStatus | undefined {
  if (!status) {
    return undefined;
  }
  if (status.configured) {
    return 'configured';
  }
  return status.hasApiKey ? 'failed' : 'needsKey';
}

function TestConnectionButton({
  status,
  label,
  disabled,
  onClick,
}: {
  status: TestStatus;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || status === 'testing'}
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
    >
      {status === 'testing' && <IconLoader className="h-3 w-3 animate-spin" />}
      {status === 'success' && <IconCheckCircle className="h-3 w-3 text-green-500" />}
      {status === 'error' && <IconXCircle className="h-3 w-3 text-red-500" />}
      {label}
    </button>
  );
}

const MediaGenerationSection = memo(() => {
  const t = useTranslations('settings.mediaGeneration');

  const { imageGeneration, videoGeneration, setImageGeneration, setVideoGeneration } = useConfigStore(
    useShallow((s) => ({
      imageGeneration: s.imageGeneration,
      videoGeneration: s.videoGeneration,
      setImageGeneration: s.setImageGeneration,
      setVideoGeneration: s.setVideoGeneration,
    })),
  );
  const providers = useProviderStore((s) => s.providers);
  const addApiKey = useProviderStore((s) => s.addApiKey);

  const [imageTestStatus, setImageTestStatus] = useState<TestStatus>('idle');
  const [videoTestStatus, setVideoTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [providerStatuses, setProviderStatuses] = useState<Record<string, MediaProviderStatus>>({});

  const [videoApiKey, setVideoApiKey] = useState('');
  const [savingVideoKey, setSavingVideoKey] = useState(false);
  const [imageApiKey, setImageApiKey] = useState('');
  const [savingImageKey, setSavingImageKey] = useState(false);

  useEffect(() => {
    fetchMediaProviderStatus().then(setProviderStatuses);
  }, []);

  const imageModel = imageGeneration?.model ?? '';
  const videoProvider: string = videoGeneration?.provider ?? '';
  const videoModel = videoGeneration?.model ?? '';

  const imageKeyProvider = isImageModelSelected(imageModel) ? resolveImageProviderId(imageModel) : undefined;
  const imageKeyStatus: KeyStatus | undefined =
    imageKeyProvider === undefined
      ? undefined
      : providerHasActiveApiKey(providers, imageKeyProvider)
        ? 'configured'
        : 'needsKey';

  const handleTestImage = useCallback(async () => {
    if (imageKeyProvider === undefined) {
      return;
    }
    setImageTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testMediaConfig('image', imageKeyProvider, imageModel);
      setImageTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) {
        setTestMessage(result.message);
      }
    } catch {
      setImageTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setImageTestStatus('idle'), 3000);
  }, [imageKeyProvider, imageModel]);

  const handleTestVideo = useCallback(async () => {
    setVideoTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testMediaConfig('video', videoProvider, videoModel);
      setVideoTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) {
        setTestMessage(result.message);
      }
    } catch {
      setVideoTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setVideoTestStatus('idle'), 3000);
  }, [videoProvider, videoModel]);

  const handleImageModelChange = useCallback(
    (model: string) => {
      setImageGeneration(withImageModel(imageGeneration, model));
    },
    [imageGeneration, setImageGeneration],
  );

  const handleVideoProviderChange = useCallback(
    (provider: string) => {
      const status = providerStatuses[provider];
      setVideoGeneration({
        ...VIDEO_CONFIG_BASE,
        ...videoGeneration,
        provider: provider as VideoGenerationProvider,
        model: status?.defaultModel || status?.models?.[0]?.id || '',
      });
    },
    [videoGeneration, setVideoGeneration, providerStatuses],
  );

  const handleVideoModelChange = useCallback(
    (model: string) => {
      if (!videoGeneration) {
        return;
      }
      setVideoGeneration({ ...videoGeneration, model });
    },
    [videoGeneration, setVideoGeneration],
  );

  const handleSaveVideoApiKey = useCallback(async () => {
    const configId = videoProviderConfigId(videoProvider);
    if (!videoApiKey.trim() || !configId) {
      return;
    }

    setSavingVideoKey(true);
    try {
      addApiKey(configId, videoApiKey.trim(), 'Video Generation');

      await syncSettings();

      setProviderStatuses(await fetchMediaProviderStatus());
      setVideoApiKey('');

      toast.success(t('apiKeySaved'));
    } catch (error) {
      console.error('Failed to save API Key:', error);
      toast.error(t('apiKeySaveFailed'));
    } finally {
      setSavingVideoKey(false);
    }
  }, [videoProvider, videoApiKey, addApiKey, t]);

  const handleSaveImageApiKey = useCallback(async () => {
    if (!imageApiKey.trim() || imageKeyProvider === undefined) {
      return;
    }

    setSavingImageKey(true);
    try {
      addApiKey(imageKeyProvider, imageApiKey.trim(), 'Image Generation');
      // A provider the app has no row for keeps no key: say so instead of reporting a save that did not happen.
      if (!providerHasActiveApiKey(useProviderStore.getState().providers, imageKeyProvider)) {
        throw new Error(`No provider row to hold the key of '${imageKeyProvider}'`);
      }

      await syncSettings();
      setImageApiKey('');

      toast.success(t('apiKeySaved'));
    } catch (error) {
      console.error('Failed to save API Key:', error);
      toast.error(t('apiKeySaveFailed'));
    } finally {
      setSavingImageKey(false);
    }
  }, [imageApiKey, imageKeyProvider, addApiKey, t]);

  const videoProviderOptions =
    Object.keys(providerStatuses).length > 0
      ? Object.entries(providerStatuses).map(([id, status]) => ({
          value: id,
          label: status.name,
          description: status.defaultModel ?? '',
        }))
      : FALLBACK_VIDEO_PROVIDERS;

  const currentProviderStatus = providerStatuses[videoProvider];
  const currentVideoKeyStatus = videoKeyStatus(currentProviderStatus);
  const videoModelOptions =
    currentProviderStatus?.models && currentProviderStatus.models.length > 0
      ? currentProviderStatus.models.map((m) => ({
          value: m.id,
          label: m.name,
        }))
      : currentProviderStatus?.defaultModel
        ? [{ value: currentProviderStatus.defaultModel, label: currentProviderStatus.defaultModel }]
        : [];

  return (
    <div className="space-y-8">
      <SettingsSection title={t('imageTitle')} description={t('imageDescription')}>
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">{t('model')}</label>
              {imageKeyStatus && <KeyStatusBadge status={imageKeyStatus} t={t} />}
            </div>
            <OptionSelect
              value={imageModel}
              options={IMAGE_MODEL_OPTIONS}
              onChange={handleImageModelChange}
              placeholder={t(selectionPlaceholderKey(imageModel, IMAGE_MODEL_OPTIONS))}
              hideDescription={false}
            />
          </div>

          {imageKeyStatus === 'needsKey' && (
            <MediaApiKeyForm
              hint={t('apiKeyHint')}
              label={t('apiKey')}
              placeholder={t('enterApiKey')}
              saveLabel={t('save')}
              value={imageApiKey}
              onChange={setImageApiKey}
              onSave={handleSaveImageApiKey}
              saving={savingImageKey}
            />
          )}

          <TestConnectionButton
            status={imageTestStatus}
            label={t('testConnection')}
            disabled={imageKeyProvider === undefined}
            onClick={handleTestImage}
          />
          {imageTestStatus === 'error' && testMessage && <p className="text-xs text-red-500">{testMessage}</p>}
        </div>
      </SettingsSection>

      <SettingsSection title={t('videoTitle')} description={t('videoDescription')}>
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">{t('provider')}</label>
              {currentVideoKeyStatus && <KeyStatusBadge status={currentVideoKeyStatus} t={t} />}
            </div>
            <OptionSelect
              value={videoProvider}
              options={videoProviderOptions}
              onChange={handleVideoProviderChange}
              placeholder={t(selectionPlaceholderKey(videoProvider, videoProviderOptions))}
              hideDescription={false}
            />
          </div>

          {currentProviderStatus && !currentProviderStatus.hasApiKey && (
            <MediaApiKeyForm
              hint={t('apiKeyHint')}
              label={t('apiKey')}
              placeholder={t('enterApiKey')}
              saveLabel={t('save')}
              value={videoApiKey}
              onChange={setVideoApiKey}
              onSave={handleSaveVideoApiKey}
              saving={savingVideoKey}
            />
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">{t('model')}</label>
            <OptionSelect
              value={videoModel}
              options={videoModelOptions}
              onChange={handleVideoModelChange}
              placeholder={t(
                currentProviderStatus ? selectionPlaceholderKey(videoModel, videoModelOptions) : 'selectPlaceholder',
              )}
              disabled={!currentProviderStatus}
              hideDescription={false}
            />
          </div>
          <TestConnectionButton
            status={videoTestStatus}
            label={t('testConnection')}
            disabled={!currentProviderStatus}
            onClick={handleTestVideo}
          />
          {videoTestStatus === 'error' && testMessage && <p className="text-xs text-red-500">{testMessage}</p>}
        </div>
      </SettingsSection>

      <TtsGenerationSection />
    </div>
  );
});

MediaGenerationSection.displayName = 'MediaGenerationSection';

export default MediaGenerationSection;
