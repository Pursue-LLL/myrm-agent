import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';

import { ModelSelectEnvProvider, type ModelSelectEnv } from '../default-model/ModelSelectRow';
import VideoFallbackCard from '../default-model/VideoFallbackCard';
import VisionFallbackCard from '../default-model/VisionFallbackCard';

const mocks = vi.hoisted(() => ({
  vision: vi.fn(),
  video: vi.fn(),
  forceSync: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('@/components/features/settings/default-model/EnabledModelSelect', () => ({
  default: () => <div data-testid="select" />,
}));
vi.mock('@/services/llm-config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/llm-config')>()),
  checkVisionFallbackHealth: mocks.vision,
  checkVideoFallbackHealth: mocks.video,
}));
vi.mock('@/services/config/ConfigSyncManager', () => ({
  getConfigSyncManager: () => ({ forceSync: mocks.forceSync, set: vi.fn() }),
}));
vi.mock('sonner', () => ({ toast: { success: mocks.toastSuccess, error: vi.fn() } }));

const ENV: ModelSelectEnv = {
  enabledModels: [],
  providers: [],
  isModelRestricted: () => false,
  openModelConfig: vi.fn(),
};
const NONE = { primary: null, fallback: null };
const EMPTY: DefaultModelConfig = { baseModel: NONE, liteModel: NONE, fastModeModel: null, routingConfig: null };
const PROVIDER: ProviderConfig = {
  id: 'p1',
  routingProfile: 'p1',
  name: 'Provider One',
  isBuiltIn: true,
  isEnabled: true,
  apiKeys: [{ id: 'k', key: 'sk-test', remark: '', isActive: true }],
  apiUrl: '',
  enabledModels: ['text-model', 'vision-model'],
  availableModels: [],
};
const modelInfo = (supportsVision: boolean) => ({
  source: 'user' as const,
  lastUpdated: '',
  supports_vision: supportsVision,
});

function seed(config: DefaultModelConfig = EMPTY, visionModels: string[] = ['vision-model']) {
  useProviderStore.setState({
    providers: [PROVIDER],
    defaultModelConfig: config,
    customModelInfo: {
      'p1/text-model': modelInfo(false),
      ...Object.fromEntries(visionModels.map((model) => [`p1/${model}`, modelInfo(true)])),
    },
  });
}

function renderCards() {
  render(
    <ModelSelectEnvProvider value={ENV}>
      <VisionFallbackCard />
      <VideoFallbackCard />
    </ModelSelectEnvProvider>,
  );
}

beforeEach(() => {
  Object.values(mocks).forEach((mock) => mock.mockReset());
  seed();
});
afterEach(cleanup);

describe('fallback health check', () => {
  it('reports a healthy endpoint, and a resolved model that differs from the configured one', async () => {
    mocks.vision.mockResolvedValue({
      configured: true,
      healthy: true,
      latency_ms: 12,
      model: 'a',
      resolved_model: 'b',
    });
    renderCards();

    fireEvent.click(screen.getByText('visionHealthTest'));

    expect(await screen.findByText('visionHealthOk')).toBeInTheDocument();
    expect(screen.getByText('visionHealthOkHint')).toBeInTheDocument();
    expect(screen.getByText('visionHealthResolvedModel')).toBeInTheDocument();
  });

  it('reports a failing endpoint with the model and the address that were probed', async () => {
    mocks.vision.mockResolvedValue({
      configured: true,
      healthy: false,
      error: 'boom',
      model: 'm',
      base_url: 'http://endpoint',
    });
    renderCards();

    fireEvent.click(screen.getByText('visionHealthTest'));

    expect(await screen.findByText('visionHealthFailed')).toBeInTheDocument();
    expect(screen.getByText('visionHealthFailedModel')).toBeInTheDocument();
    expect(screen.getByText('visionHealthFailedEndpoint')).toBeInTheDocument();
  });

  it('reports a fallback that is not configured', async () => {
    mocks.vision.mockResolvedValue({ configured: false, healthy: false });
    renderCards();

    fireEvent.click(screen.getByText('visionHealthTest'));

    expect(await screen.findByText('visionHealthNotConfigured')).toBeInTheDocument();
  });

  it('stays usable after the probe request itself fails', async () => {
    mocks.vision.mockRejectedValueOnce(new Error('network')).mockResolvedValue({ configured: true, healthy: true });
    renderCards();

    fireEvent.click(screen.getByText('visionHealthTest'));
    await waitFor(() => expect(screen.getByText('visionHealthTest')).toBeEnabled());
    fireEvent.click(screen.getByText('visionHealthTest'));

    expect(await screen.findByText('visionHealthOk')).toBeInTheDocument();
    expect(mocks.vision).toHaveBeenCalledTimes(2);
  });

  it('probes the video endpoint from the video card only', async () => {
    mocks.video.mockResolvedValue({ configured: true, healthy: true, latency_ms: 3 });
    renderCards();

    fireEvent.click(screen.getByText('videoHealthTest'));

    expect(await screen.findByText('videoHealthOk')).toBeInTheDocument();
    expect(mocks.video).toHaveBeenCalledTimes(1);
    expect(mocks.vision).not.toHaveBeenCalled();
  });
});

describe('vision fallback recommendation', () => {
  it('applies the suggested model as the vision fallback, syncs, and probes it', async () => {
    mocks.vision.mockResolvedValue({ configured: true, healthy: true });
    renderCards();

    fireEvent.click(screen.getByText('visionRecommendButton'));

    await waitFor(() => expect(mocks.vision).toHaveBeenCalledTimes(1));
    // Only the model is saved: the provider's display name used for the preview must not leak into the config.
    expect(useProviderStore.getState().defaultModelConfig.visionFallbackModel?.primary).toStrictEqual({
      providerId: 'p1',
      model: 'vision-model',
    });
    expect(mocks.toastSuccess).toHaveBeenCalledWith('visionRecommendApplied');
    expect(mocks.forceSync).toHaveBeenCalledTimes(1);
  });

  it.each<[string, DefaultModelConfig, string[]]>([
    [
      'the base model already reads images',
      { ...EMPTY, baseModel: { primary: { providerId: 'p1', model: 'vision-model' }, fallback: null } },
      ['vision-model'],
    ],
    [
      'a vision fallback is already chosen',
      { ...EMPTY, visionFallbackModel: { primary: { providerId: 'p1', model: 'text-model' }, fallback: null } },
      ['vision-model'],
    ],
    ['no enabled model reads images', EMPTY, []],
  ])('is not offered when %s', (_case, config, visionModels) => {
    seed(config, visionModels);

    renderCards();

    expect(screen.queryByText('visionRecommendButton')).not.toBeInTheDocument();
  });
});
