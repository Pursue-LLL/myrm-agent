'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useShallow } from 'zustand/react/shallow';
import {
  IconLoader,
  IconCheckCircle,
  IconXCircle,
  IconAlertCircle,
  IconEye,
  IconEyeOff,
  IconSave,
} from '@/components/ui/icons/PremiumIcons';
import { getBackendUrl } from '@/lib/utils/apiConfig';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import { toast } from '@/hooks/useToast';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';
import type { ImageGenerationConfig, VideoGenerationConfig, VideoGenerationProvider } from '@/services/config/types';
import OptionSelect from '../OptionSelect';
import SettingsSection from './SettingsSection';

const IMAGE_MODEL_OPTIONS = [
  { value: 'dall-e-3', label: 'DALL·E 3', description: 'OpenAI' },
  { value: 'dall-e-2', label: 'DALL·E 2', description: 'OpenAI' },
  { value: 'gpt-image-1', label: 'GPT Image 1', description: 'OpenAI' },
  { value: 'gemini/imagen-3.0-generate-002', label: 'Imagen 3.0', description: 'Google' },
  { value: 'flux/schnell', label: 'Flux Schnell', description: 'Together AI' },
  { value: 'flux/pro', label: 'Flux Pro', description: 'Together AI' },
  { value: 'stability/stable-diffusion-xl', label: 'SDXL', description: 'Stability AI' },
];

const FALLBACK_VIDEO_PROVIDERS: {
  value: VideoGenerationProvider;
  label: string;
  description: string;
}[] = [
  { value: 'openai', label: 'OpenAI Sora', description: 'sora / sora-2' },
  { value: 'gemini', label: 'Google Veo', description: 'veo-3.1-fast-generate-preview' },
  { value: 'qwen', label: 'Qwen Wan', description: 'wan2.6-t2v' },
  { value: 'minimax', label: 'MiniMax Hailuo', description: 'MiniMax-Hailuo-2.3' },
];

const PROVIDER_CONFIG_IDS: Record<VideoGenerationProvider, string> = {
  openai: 'openai',
  gemini: 'gemini',
  qwen: 'dashscope',
  minimax: 'minimax',
};

const DEFAULT_IMAGE_CONFIG: ImageGenerationConfig = {
  model: 'dall-e-3',
  fallbackModels: [],
  defaultSize: '1024x1024',
  defaultQuality: 'standard',
  timeoutSeconds: 120,
  maxRetries: 1,
};

const DEFAULT_VIDEO_CONFIG: VideoGenerationConfig = {
  provider: 'openai',
  model: 'sora',
  fallbackProviders: [],
  timeoutSeconds: 300,
  maxRetries: 1,
};

type TestStatus = 'idle' | 'testing' | 'success' | 'error';

interface ProviderStatus {
  name: string;
  hasApiKey: boolean;
  healthy: boolean;
  configured: boolean;
  defaultModel?: string;
  models?: Array<{ id: string; name: string }>;
}

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

async function fetchProviderStatus(): Promise<Record<string, ProviderStatus>> {
  try {
    const resp = await fetch(`${getBackendUrl()}/api/v1/agents/media-provider-status`, {
      headers: getAuthHeaders(),
    });
    const data = await resp.json();
    if (data.success && data.data?.providers) {
      return data.data.providers as Record<string, ProviderStatus>;
    }
  } catch {
    /* network error — silently fall back to empty */
  }
  return {};
}

function ProviderStatusBadge({
  provider: _provider,
  status,
  t,
}: {
  provider: VideoGenerationProvider;
  status: ProviderStatus | undefined;
  t: ReturnType<typeof useTranslations>;
}) {
  if (!status) return null;

  if (status.configured) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
        <IconCheckCircle className="h-3 w-3" />
        {t('configured')}
      </span>
    );
  }

  if (!status.hasApiKey) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
        <IconAlertCircle className="h-3 w-3" />
        {t('needsApiKey')}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-xs text-red-500">
      <IconXCircle className="h-3 w-3" />
      {t('connectionFailed')}
    </span>
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

  const [imageTestStatus, setImageTestStatus] = useState<TestStatus>('idle');
  const [videoTestStatus, setVideoTestStatus] = useState<TestStatus>('idle');
  const [testMessage, setTestMessage] = useState('');
  const [providerStatuses, setProviderStatuses] = useState<Record<string, ProviderStatus>>({});

  const [videoApiKey, setVideoApiKey] = useState('');
  const [showVideoApiKey, setShowVideoApiKey] = useState(false);
  const [savingVideoKey, setSavingVideoKey] = useState(false);

  const [imageApiKey, setImageApiKey] = useState('');
  const [showImageApiKey, setShowImageApiKey] = useState(false);
  const [savingImageKey, setSavingImageKey] = useState(false);
  const [imageProviderStatus, setImageProviderStatus] = useState<ProviderStatus | undefined>();

  const addApiKey = useProviderStore((s) => s.addApiKey);

  useEffect(() => {
    fetchProviderStatus().then((statuses) => {
      setProviderStatuses(statuses);
      setImageProviderStatus(statuses['openai']);
    });
  }, []);

  const imageModel = imageGeneration?.model ?? DEFAULT_IMAGE_CONFIG.model;
  const videoProvider = videoGeneration?.provider ?? DEFAULT_VIDEO_CONFIG.provider;
  const videoModel = videoGeneration?.model ?? DEFAULT_VIDEO_CONFIG.model;

  const handleTestImage = useCallback(async () => {
    setImageTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testMediaConfig('image', 'openai', imageModel);
      setImageTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) setTestMessage(result.message);
    } catch {
      setImageTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setImageTestStatus('idle'), 3000);
  }, [imageModel]);

  const handleTestVideo = useCallback(async () => {
    setVideoTestStatus('testing');
    setTestMessage('');
    try {
      const result = await testMediaConfig('video', videoProvider, videoModel);
      setVideoTestStatus(result.ok ? 'success' : 'error');
      if (!result.ok) setTestMessage(result.message);
    } catch {
      setVideoTestStatus('error');
      setTestMessage('Network error');
    }
    setTimeout(() => setVideoTestStatus('idle'), 3000);
  }, [videoProvider, videoModel]);

  const handleImageModelChange = useCallback(
    (model: string) => {
      setImageGeneration({ ...(imageGeneration ?? DEFAULT_IMAGE_CONFIG), model });
    },
    [imageGeneration, setImageGeneration],
  );

  const handleVideoProviderChange = useCallback(
    (provider: string) => {
      const p = provider as VideoGenerationProvider;
      const status = providerStatuses[p];
      const defaultModel = status?.defaultModel ?? status?.models?.[0]?.id ?? 'sora';
      setVideoGeneration({
        ...(videoGeneration ?? DEFAULT_VIDEO_CONFIG),
        provider: p,
        model: defaultModel,
      });
    },
    [videoGeneration, setVideoGeneration, providerStatuses],
  );

  const handleVideoModelChange = useCallback(
    (model: string) => {
      setVideoGeneration({ ...(videoGeneration ?? DEFAULT_VIDEO_CONFIG), model });
    },
    [videoGeneration, setVideoGeneration],
  );

  const handleSaveVideoApiKey = useCallback(async () => {
    if (!videoApiKey.trim()) return;

    setSavingVideoKey(true);
    try {
      const configId = PROVIDER_CONFIG_IDS[videoProvider];
      addApiKey(configId, videoApiKey.trim(), 'Video Generation');

      await getConfigSyncManager().forceSync();

      const newStatuses = await fetchProviderStatus();
      setProviderStatuses(newStatuses);
      setVideoApiKey('');

      toast.success(t('apiKeySaved') || 'API Key saved successfully!');
    } catch (error) {
      console.error('Failed to save API Key:', error);
      toast.error(t('apiKeySaveFailed') || 'Failed to save API Key');
    } finally {
      setSavingVideoKey(false);
    }
  }, [videoProvider, videoApiKey, addApiKey, t]);

  const handleSaveImageApiKey = useCallback(async () => {
    if (!imageApiKey.trim()) return;

    setSavingImageKey(true);
    try {
      addApiKey('openai', imageApiKey.trim(), 'Image Generation');

      await getConfigSyncManager().forceSync();

      const newStatuses = await fetchProviderStatus();
      setImageProviderStatus(newStatuses['openai']);
      setImageApiKey('');

      toast.success(t('apiKeySaved') || 'API Key saved successfully!');
    } catch (error) {
      console.error('Failed to save API Key:', error);
      toast.error(t('apiKeySaveFailed') || 'Failed to save API Key');
    } finally {
      setSavingImageKey(false);
    }
  }, [imageApiKey, addApiKey, t]);

  const videoProviderOptions =
    Object.keys(providerStatuses).length > 0
      ? Object.entries(providerStatuses).map(([id, status]) => ({
          value: id,
          label: status.name,
          description: status.defaultModel ?? '',
        }))
      : FALLBACK_VIDEO_PROVIDERS;

  const currentProviderStatus = providerStatuses[videoProvider];
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
              {imageProviderStatus &&
                (imageProviderStatus.configured ? (
                  <span className="inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                    <IconCheckCircle className="h-3 w-3" />
                    {t('configured')}
                  </span>
                ) : !imageProviderStatus.hasApiKey ? (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                    <IconAlertCircle className="h-3 w-3" />
                    {t('needsApiKey')}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-red-500">
                    <IconXCircle className="h-3 w-3" />
                    {t('connectionFailed')}
                  </span>
                ))}
            </div>
            <OptionSelect
              value={imageModel}
              options={IMAGE_MODEL_OPTIONS}
              onChange={handleImageModelChange}
              hideDescription={false}
            />
          </div>

          {imageProviderStatus && !imageProviderStatus.hasApiKey && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30 p-3 space-y-3">
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {t('apiKeyHint') ||
                  'Please configure the API Key for this provider. The key will be shared globally across all features.'}
              </p>
              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">{t('apiKey') || 'API Key'}</label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type={showImageApiKey ? 'text' : 'password'}
                      value={imageApiKey}
                      onChange={(e) => setImageApiKey(e.target.value)}
                      placeholder={t('enterApiKey') || 'Enter API Key'}
                      className="w-full rounded-full border border-border bg-background px-3 py-1.5 text-sm pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowImageApiKey(!showImageApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showImageApiKey ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveImageApiKey}
                    disabled={!imageApiKey.trim() || savingImageKey}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                  >
                    {savingImageKey ? (
                      <IconLoader className="h-3 w-3 animate-spin" />
                    ) : (
                      <IconSave className="h-3 w-3" />
                    )}
                    {t('save') || 'Save'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={handleTestImage}
            disabled={imageTestStatus === 'testing'}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {imageTestStatus === 'testing' && <IconLoader className="h-3 w-3 animate-spin" />}
            {imageTestStatus === 'success' && <IconCheckCircle className="h-3 w-3 text-green-500" />}
            {imageTestStatus === 'error' && <IconXCircle className="h-3 w-3 text-red-500" />}
            {t('testConnection')}
          </button>
          {imageTestStatus === 'error' && testMessage && <p className="text-xs text-red-500">{testMessage}</p>}
        </div>
      </SettingsSection>

      <SettingsSection title={t('videoTitle')} description={t('videoDescription')}>
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">{t('provider')}</label>
              <ProviderStatusBadge provider={videoProvider} status={providerStatuses[videoProvider]} t={t} />
            </div>
            <OptionSelect
              value={videoProvider}
              options={videoProviderOptions}
              onChange={handleVideoProviderChange}
              hideDescription={false}
            />
          </div>

          {currentProviderStatus && !currentProviderStatus.hasApiKey && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/30 p-3 space-y-3">
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {t('apiKeyHint') ||
                  'Please configure the API Key for this provider. The key will be shared globally across all features.'}
              </p>
              <div className="space-y-2">
                <label className="text-xs font-medium text-foreground">{t('apiKey') || 'API Key'}</label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type={showVideoApiKey ? 'text' : 'password'}
                      value={videoApiKey}
                      onChange={(e) => setVideoApiKey(e.target.value)}
                      placeholder={t('enterApiKey') || 'Enter API Key'}
                      className="w-full rounded-full border border-border bg-background px-3 py-1.5 text-sm pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowVideoApiKey(!showVideoApiKey)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showVideoApiKey ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveVideoApiKey}
                    disabled={!videoApiKey.trim() || savingVideoKey}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                  >
                    {savingVideoKey ? (
                      <IconLoader className="h-3 w-3 animate-spin" />
                    ) : (
                      <IconSave className="h-3 w-3" />
                    )}
                    {t('save') || 'Save'}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">{t('model')}</label>
            <OptionSelect
              value={videoModel}
              options={videoModelOptions}
              onChange={handleVideoModelChange}
              hideDescription={false}
            />
          </div>
          <button
            type="button"
            onClick={handleTestVideo}
            disabled={videoTestStatus === 'testing'}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            {videoTestStatus === 'testing' && <IconLoader className="h-3 w-3 animate-spin" />}
            {videoTestStatus === 'success' && <IconCheckCircle className="h-3 w-3 text-green-500" />}
            {videoTestStatus === 'error' && <IconXCircle className="h-3 w-3 text-red-500" />}
            {t('testConnection')}
          </button>
          {videoTestStatus === 'error' && testMessage && <p className="text-xs text-red-500">{testMessage}</p>}
        </div>
      </SettingsSection>
    </div>
  );
});

MediaGenerationSection.displayName = 'MediaGenerationSection';

export default MediaGenerationSection;
