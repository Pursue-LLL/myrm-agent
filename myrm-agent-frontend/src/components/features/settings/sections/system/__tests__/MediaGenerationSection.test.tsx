import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MediaProviderStatus } from '@/lib/utils/media';
import MediaGenerationSection from '../MediaGenerationSection';

interface ProviderRow {
  id: string;
  isEnabled: boolean;
  routingProfile: string;
  apiKeys: Array<{ key: string; isActive: boolean }>;
}

const kit = vi.hoisted(() => ({
  config: {} as Record<string, unknown>,
  providers: [] as ProviderRow[],
  statuses: {} as Record<string, unknown>,
  setImageGeneration: vi.fn(),
  setVideoGeneration: vi.fn(),
  addApiKey: vi.fn<(providerId: string, key: string, remark: string) => void>(),
  forceSync: vi.fn(async () => undefined),
  success: vi.fn<(text: string) => void>(),
  error: vi.fn<(text: string) => void>(),
  fetch: vi.fn<(url: string, init: RequestInit) => Promise<{ json: () => Promise<unknown> }>>(),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/store/useConfigStore', () => ({
  default: (select: (state: object) => unknown) =>
    select({
      ...kit.config,
      setImageGeneration: kit.setImageGeneration,
      setVideoGeneration: kit.setVideoGeneration,
    }),
}));
vi.mock('@/store/useProviderStore', () => {
  const useProviderStore = (select: (state: object) => unknown) =>
    select({ providers: kit.providers, addApiKey: kit.addApiKey });
  return { default: Object.assign(useProviderStore, { getState: () => ({ providers: kit.providers }) }) };
});
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: kit.success, error: kit.error } }));
vi.mock('@/services/config/ConfigSyncManager', () => ({ getConfigSyncManager: () => ({ forceSync: kit.forceSync }) }));
vi.mock('@/lib/utils/apiConfig', () => ({ getBackendUrl: () => 'http://backend' }));
vi.mock('@/lib/utils/authHeaders', () => ({ getAuthHeaders: () => ({ Authorization: 'Bearer token' }) }));
vi.mock('@/lib/utils/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/media')>()),
  fetchMediaProviderStatus: async () => kit.statuses,
}));
// The speech card has its own tests.
vi.mock('../TtsGenerationSection', () => ({ default: () => null }));

const status = (overrides: Partial<MediaProviderStatus> = {}): MediaProviderStatus => ({
  name: 'Google Veo',
  hasApiKey: true,
  healthy: true,
  configured: true,
  defaultModel: 'veo-3.1-fast-generate-preview',
  models: [
    { id: 'veo-3.1-fast-generate-preview', name: 'Veo 3.1 Fast' },
    { id: 'veo-3.1-generate-preview', name: 'Veo 3.1' },
  ],
  ...overrides,
});

const providerWithKey = (id: string): ProviderRow => ({
  id,
  isEnabled: true,
  routingProfile: id,
  apiKeys: [{ key: 'sk-live', isActive: true }],
});

const imageConfig = (overrides: Record<string, unknown> = {}) => ({
  model: 'gpt-image-2.6-sunburst',
  fallbackModels: [],
  defaultSize: '1024x1024',
  timeoutSeconds: 120,
  maxRetries: 1,
  ...overrides,
});

const emptyDropdowns = () => screen.queryAllByRole('button', { name: 'Select…' });
const testButtons = () => screen.getAllByRole('button', { name: 'Test Connection' });

async function renderSection() {
  const view = render(<MediaGenerationSection />);
  await act(async () => undefined);
  return view;
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.config = {};
  kit.providers = [];
  kit.statuses = {
    gemini: status(),
    xai: status({ name: 'xAI Grok', defaultModel: 'grok-imagine-video', models: [] }),
  };
  kit.forceSync.mockResolvedValue(undefined);
  kit.addApiKey.mockImplementation((providerId, key) => {
    kit.providers = [...kit.providers, { ...providerWithKey(providerId), apiKeys: [{ key, isActive: true }] }];
  });
  vi.stubGlobal('fetch', kit.fetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MediaGenerationSection with nothing chosen', () => {
  it('asks for every choice, fills in none and writes nothing', async () => {
    await renderSection();

    // Image model and video provider ask; the video model waits for its provider.
    expect(emptyDropdowns()).toHaveLength(3);
    expect(emptyDropdowns()[2]).toBeDisabled();
    expect(screen.queryByText('API Key Required')).toBeNull();
    expect(screen.queryByText('Configured')).toBeNull();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
    for (const button of testButtons()) {
      expect(button).toBeDisabled();
    }
    expect(kit.setImageGeneration).not.toHaveBeenCalled();
    expect(kit.setVideoGeneration).not.toHaveBeenCalled();
  });

  it('offers exactly the models the engine ships and none a vendor has retired', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[0]);

    for (const [label, vendor] of [
      ['GPT Image 2.6 Sunburst', 'OpenAI'],
      ['GPT Image 2.6 Flare', 'OpenAI'],
      ['Imagen 3.0', 'Google'],
      ['Flux Schnell', 'Together AI'],
      ['Flux Pro', 'Together AI'],
      ['SDXL', 'Stability AI'],
      ['Grok Imagine', 'xAI'],
      ['Grok Imagine Quality', 'xAI'],
    ]) {
      expect(screen.getByRole('button', { name: new RegExp(`^${label}\\s*${vendor}$`) })).toBeInTheDocument();
    }
    expect(screen.queryByText(/DALL/)).toBeNull();
    expect(screen.queryByText('GPT Image 1')).toBeNull();
  });

  it('keeps the settings that are not the choice when a first model is chosen', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[0]);
    await user.click(screen.getByRole('button', { name: /^Flux Pro/ }));

    expect(kit.setImageGeneration).toHaveBeenCalledExactlyOnceWith({
      model: 'flux/pro',
      fallbackModels: [],
      defaultSize: '1024x1024',
      timeoutSeconds: 120,
      maxRetries: 1,
    });
  });

  it('lists the six video providers while the server has not listed its own, and no OpenAI Sora', async () => {
    kit.statuses = {};
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[1]);

    for (const label of ['Google Veo', 'Qwen Wan', 'MiniMax Hailuo', 'xAI Grok', 'FAL.ai', 'Volcengine Seedance']) {
      expect(screen.getByRole('button', { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
    expect(screen.queryByText(/Sora/)).toBeNull();
  });
});

describe('MediaGenerationSection image choice', () => {
  it('asks to choose again for a stored model the engine no longer offers, and does not call it configured', async () => {
    kit.config = { imageGeneration: imageConfig({ model: 'dall-e-3', defaultQuality: 'standard' }) };
    kit.providers = [providerWithKey('openai')];

    await renderSection();

    expect(screen.getByRole('button', { name: 'Select again' })).toBeInTheDocument();
    expect(screen.queryByText('Configured')).toBeNull();
    expect(testButtons()[0]).toBeDisabled();
  });

  it('carries only the settings the app keeps into the new choice', async () => {
    kit.config = {
      imageGeneration: imageConfig({
        model: 'dall-e-3',
        fallbackModels: ['flux/schnell'],
        defaultSize: '1536x1024',
        defaultQuality: 'standard',
        timeoutSeconds: 30,
        maxRetries: 3,
      }),
    };
    const user = userEvent.setup();
    await renderSection();

    await user.click(screen.getByRole('button', { name: 'Select again' }));
    await user.click(screen.getByRole('button', { name: /^GPT Image 2.6 Flare/ }));

    expect(kit.setImageGeneration).toHaveBeenCalledExactlyOnceWith({
      model: 'gpt-image-2.6-flare',
      fallbackModels: ['flux/schnell'],
      defaultSize: '1536x1024',
      timeoutSeconds: 30,
      maxRetries: 3,
    });
  });

  it("judges the key by the chosen model's own provider", async () => {
    kit.config = { imageGeneration: imageConfig({ model: 'flux/pro' }) };
    kit.providers = [providerWithKey('openai')];

    await renderSection();
    expect(screen.getByText('API Key Required')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter API Key')).toBeInTheDocument();
  });

  it('shows the key as configured, and no key form, once the provider has one', async () => {
    kit.config = { imageGeneration: imageConfig() };
    kit.providers = [providerWithKey('openai')];

    await renderSection();

    expect(screen.getByText('Configured')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('saves the key under the provider of the chosen model', async () => {
    kit.config = { imageGeneration: imageConfig({ model: 'xai/grok-imagine-image' }) };
    kit.statuses = {};
    const user = userEvent.setup();
    await renderSection();

    await user.type(screen.getByPlaceholderText('Enter API Key'), '  sk-new ');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(kit.success).toHaveBeenCalledWith('API Key saved successfully'));
    expect(kit.addApiKey).toHaveBeenCalledExactlyOnceWith('xai', 'sk-new', 'Image Generation');
    expect(kit.forceSync).toHaveBeenCalledTimes(1);
  });

  it('says the key was not saved when the app has no provider row to hold it', async () => {
    kit.config = { imageGeneration: imageConfig({ model: 'stability/stable-diffusion-xl' }) };
    kit.statuses = {};
    kit.addApiKey.mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const user = userEvent.setup();
    await renderSection();

    await user.type(screen.getByPlaceholderText('Enter API Key'), 'sk-new');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(kit.error).toHaveBeenCalledWith('Failed to save API Key'));
    expect(kit.success).not.toHaveBeenCalled();
    expect(kit.forceSync).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Enter API Key')).toHaveValue('sk-new');
  });

  it('tests the connection of the chosen model with its own provider', async () => {
    kit.config = { imageGeneration: imageConfig() };
    kit.providers = [providerWithKey('openai')];
    kit.fetch.mockResolvedValue({ json: async () => ({ success: true }) });
    const user = userEvent.setup();
    await renderSection();

    await user.click(testButtons()[0]);

    expect(kit.fetch).toHaveBeenCalledExactlyOnceWith('http://backend/api/v1/agents/test-media-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer token' },
      body: JSON.stringify({ mediaType: 'image', provider: 'openai', model: 'gpt-image-2.6-sunburst' }),
    });
  });
});

describe('MediaGenerationSection video choice', () => {
  it('offers the providers the server lists', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[1]);

    expect(screen.getByRole('button', { name: /^Google Veo/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^xAI Grok/ })).toBeInTheDocument();
    expect(screen.queryByText(/OpenAI/)).toBeNull();
  });

  it('asks to choose again for a stored provider the server no longer lists, and leaves the model for after', async () => {
    kit.config = {
      videoGeneration: { provider: 'openai', model: 'sora', fallbackProviders: [], timeoutSeconds: 300, maxRetries: 1 },
    };

    await renderSection();

    expect(screen.getByRole('button', { name: 'Select again' })).toBeInTheDocument();
    expect(emptyDropdowns()).toHaveLength(2);
    expect(screen.queryByRole('button', { name: 'sora' })).toBeNull();
    expect(testButtons()[1]).toBeDisabled();
  });

  it("chooses the provider's own default model along with the provider, and keeps the other settings", async () => {
    kit.config = {
      videoGeneration: {
        provider: 'xai',
        model: 'grok-imagine-video',
        fallbackProviders: [{ provider: 'gemini', model: 'veo-3.1-fast-generate-preview' }],
        timeoutSeconds: 200,
        maxRetries: 2,
        defaultAspectRatio: '16:9',
      },
    };
    const user = userEvent.setup();
    await renderSection();

    await user.click(screen.getByRole('button', { name: /^xAI Grok/ }));
    await user.click(screen.getByRole('button', { name: /^Google Veo/ }));

    expect(kit.setVideoGeneration).toHaveBeenCalledExactlyOnceWith({
      provider: 'gemini',
      model: 'veo-3.1-fast-generate-preview',
      fallbackProviders: [{ provider: 'gemini', model: 'veo-3.1-fast-generate-preview' }],
      timeoutSeconds: 200,
      maxRetries: 2,
      defaultAspectRatio: '16:9',
    });
  });

  it('chooses no model for a provider that names none, rather than a default of its own', async () => {
    kit.statuses = { gemini: status({ defaultModel: '', models: [] }) };
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[1]);
    await user.click(screen.getByRole('button', { name: /^Google Veo/ }));

    expect(kit.setVideoGeneration).toHaveBeenCalledExactlyOnceWith({
      provider: 'gemini',
      model: '',
      fallbackProviders: [],
      timeoutSeconds: 300,
      maxRetries: 1,
    });
  });

  it('asks to choose a model again when the provider no longer serves the stored one', async () => {
    kit.config = {
      videoGeneration: {
        provider: 'gemini',
        model: 'retired-model',
        fallbackProviders: [],
        timeoutSeconds: 300,
        maxRetries: 1,
      },
    };

    await renderSection();

    expect(screen.getByRole('button', { name: /Google Veo/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select again' })).toBeEnabled();
  });

  it('changes only the model when another model of the provider is chosen', async () => {
    const stored = {
      provider: 'gemini',
      model: 'veo-3.1-fast-generate-preview',
      fallbackProviders: [],
      timeoutSeconds: 300,
      maxRetries: 1,
    };
    kit.config = { videoGeneration: stored };
    const user = userEvent.setup();
    await renderSection();

    await user.click(screen.getByRole('button', { name: 'Veo 3.1 Fast' }));
    await user.click(screen.getByRole('button', { name: 'Veo 3.1' }));

    expect(kit.setVideoGeneration).toHaveBeenCalledExactlyOnceWith({ ...stored, model: 'veo-3.1-generate-preview' });
  });

  it('shows the key form of the chosen provider when it has no key, and saves under its provider-table id', async () => {
    kit.config = {
      videoGeneration: {
        provider: 'gemini',
        model: 'veo-3.1-fast-generate-preview',
        fallbackProviders: [],
        timeoutSeconds: 300,
        maxRetries: 1,
      },
    };
    kit.statuses = { gemini: status({ hasApiKey: false, configured: false }) };
    const user = userEvent.setup();
    await renderSection();
    expect(screen.getByText('API Key Required')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Enter API Key'), 'sk-video');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(kit.success).toHaveBeenCalledWith('API Key saved successfully'));
    expect(kit.addApiKey).toHaveBeenCalledExactlyOnceWith('gemini', 'sk-video', 'Video Generation');
  });
});
