import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import TtsGenerationSection from '../TtsGenerationSection';

interface VoiceRecord {
  value: Record<string, unknown>;
  meta?: { version?: string };
}

interface ApiOptions {
  method?: string;
  body?: string;
  silent?: boolean;
}

const kit = vi.hoisted(() => ({
  apiRequest: vi.fn<(path: string, options?: ApiOptions) => Promise<unknown>>(),
  providerKeyReady: vi.fn<(providers: unknown[], providerId: string) => boolean>(),
  success: vi.fn<(text: string) => void>(),
  error: vi.fn<(text: string) => void>(),
  providers: [] as unknown[],
  record: { value: {}, meta: { version: '0' } } as VoiceRecord,
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/lib/api', () => ({ apiRequest: kit.apiRequest }));
vi.mock('@/store/useProviderStore', () => ({
  default: (select: (state: { providers: unknown[] }) => unknown) => select({ providers: kit.providers }),
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: kit.success, error: kit.error } }));
vi.mock('@/lib/utils/media', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/utils/media')>()),
  providerHasActiveApiKey: kit.providerKeyReady,
}));

const openaiChosen = { ttsProvider: 'openai', ttsModel: 'tts-1', ttsVoice: 'alloy' };

const storedVoice = (overrides: Record<string, unknown> = {}): VoiceRecord => ({
  value: { sttEnabled: true, ttsMaxLength: 900, ...overrides },
  meta: { version: 'v3' },
});

/** What the server answers while no voice settings are saved: an empty value at version 0, not an error. */
const emptyVoice = (): VoiceRecord => ({ value: {}, meta: { version: '0' } });

const puts = () => kit.apiRequest.mock.calls.filter(([, options]) => options?.method === 'PUT');
const putBody = (index = 0) => JSON.parse(String(puts()[index][1]?.body)) as Record<string, unknown>;
const keyInput = () => screen.getByPlaceholderText('Enter API Key');
const saveButton = () => screen.getByRole('button', { name: 'Save' });
const eyeButton = () => keyInput().parentElement?.querySelector('button') as HTMLElement;
const emptyDropdowns = () => screen.getAllByRole('button', { name: 'Select…' });

async function renderSection() {
  const view = render(<TtsGenerationSection />);
  await act(async () => undefined);
  return view;
}

async function choose(current: RegExp | string, option: RegExp, user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: current }));
  await user.click(screen.getByRole('button', { name: option }));
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.providers = [];
  kit.record = storedVoice({ ...openaiChosen, ttsApiKey: 'sk-stored' });
  kit.providerKeyReady.mockReturnValue(false);
  kit.apiRequest.mockImplementation(async (_path, options) => (options?.method === 'PUT' ? {} : kit.record));
});

describe('TtsGenerationSection loading', () => {
  it('reads the stored voice settings quietly and shows the stored choices as configured', async () => {
    kit.record = storedVoice({
      ttsProvider: 'elevenlabs',
      ttsModel: 'eleven_multilingual_v2',
      ttsVoice: 'AZnzlk1XvdvUeBnXmlld',
      ttsApiKey: 'sk-stored',
    });

    await renderSection();

    expect(kit.apiRequest).toHaveBeenCalledWith('/config/voice', { silent: true });
    expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Multilingual v2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Domi/ })).toBeInTheDocument();
    expect(screen.getByText('Configured')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('asks for a key when neither the settings nor the provider list hold one', async () => {
    kit.record = storedVoice(openaiChosen);

    await renderSection();

    expect(screen.getByText('API Key Required')).toBeInTheDocument();
    expect(keyInput()).toBeInTheDocument();
  });

  it("counts an active key of the provider's own list as configured", async () => {
    kit.record = storedVoice(openaiChosen);
    kit.providerKeyReady.mockReturnValue(true);

    await renderSection();

    expect(kit.providerKeyReady).toHaveBeenCalledWith(kit.providers, 'openai');
    expect(screen.getByText('Configured')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('asks for every choice, fills in none and writes nothing, when the server holds no voice settings yet', async () => {
    kit.record = emptyVoice();

    await renderSection();

    const [provider, model, voice] = emptyDropdowns();
    expect(emptyDropdowns()).toHaveLength(3);
    expect(provider).toBeEnabled();
    expect(model).toBeDisabled();
    expect(voice).toBeDisabled();
    expect(screen.queryByText('Configured')).toBeNull();
    expect(screen.queryByText('API Key Required')).toBeNull();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
    expect(screen.getByRole('button', { name: 'Test Connection' })).toBeDisabled();
    expect(puts()).toHaveLength(0);
  });

  it('shows a stored model the provider does not offer as a choice to make again, not as the first model', async () => {
    kit.record = storedVoice({
      ttsProvider: 'volcengine',
      ttsModel: 'tts-1',
      ttsVoice: 'zh_female_vv_uranus_bigtts',
      ttsApiKey: 'sk-stored',
    });

    await renderSection();

    expect(screen.getByRole('button', { name: /Volcengine Speech/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select again' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Uranus/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Seed-Audio/ })).toBeNull();
  });

  it('shows a stored model of the provider as it is', async () => {
    kit.record = storedVoice({ ...openaiChosen, ttsModel: 'tts-1-hd' });

    await renderSection();

    expect(screen.getByRole('button', { name: /TTS 1 HD/ })).toBeInTheDocument();
  });

  it.each(['edge', 'piper', 'voicebox'])(
    'asks for a new provider when the settings hold %s, one only the channel voice settings offer',
    async (ttsProvider) => {
      kit.record = storedVoice({
        ttsProvider,
        ttsModel: 'gpt-4o-mini-tts',
        ttsVoice: 'en-US-AriaNeural',
        ttsApiKey: 'sk-of-another-provider',
      });

      await renderSection();

      expect(screen.getByRole('button', { name: 'Select again' })).toBeEnabled();
      expect(emptyDropdowns()).toHaveLength(2);
      for (const dropdown of emptyDropdowns()) {
        expect(dropdown).toBeDisabled();
      }
      expect(screen.queryByText('API Key Required')).toBeNull();
      expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
      expect(puts()).toHaveLength(0);
    },
  );

  it('asks for a voice when the settings name none, without offering the first one', async () => {
    kit.record = storedVoice({
      ttsProvider: 'elevenlabs',
      ttsModel: 'eleven_turbo_v2_5',
      ttsVoice: '',
      ttsApiKey: 'sk-stored',
    });

    await renderSection();

    expect(emptyDropdowns()).toHaveLength(1);
    expect(screen.queryByRole('button', { name: /Rachel/ })).toBeNull();
  });
});

describe('TtsGenerationSection choices', () => {
  it("switches to the new provider's first model and voice, saves them and drops the old provider's key", async () => {
    const user = userEvent.setup();
    await renderSection();

    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    expect(screen.getByRole('button', { name: /Turbo v2.5/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Rachel/ })).toBeInTheDocument();
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(putBody()).toEqual({
      value: {
        sttEnabled: true,
        ttsMaxLength: 900,
        ttsProvider: 'elevenlabs',
        ttsModel: 'eleven_turbo_v2_5',
        ttsVoice: '21m00Tcm4TlvDq8ikWAM',
        ttsApiKey: '',
      },
      expectedVersion: 'v3',
      deviceId: 'web',
    });
    expect(puts()[0][1]?.silent).toBe(true);
    // The old provider's key is gone, so the new provider is judged by its own key.
    expect(kit.providerKeyReady).toHaveBeenLastCalledWith(kit.providers, 'elevenlabs');
    expect(screen.getByText('API Key Required')).toBeInTheDocument();
  });

  it('saves a changed model and a changed voice, keeping the provider and its key', async () => {
    const user = userEvent.setup();
    await renderSection();

    await choose('TTS 1', /TTS 1 HD/, user);
    await choose('Alloy', /Nova/, user);

    await waitFor(() => expect(puts()).toHaveLength(2));
    expect(putBody(0).value).toMatchObject({ ttsProvider: 'openai', ttsModel: 'tts-1-hd', ttsVoice: 'alloy' });
    expect(putBody(1).value).toMatchObject({
      ttsProvider: 'openai',
      ttsModel: 'tts-1-hd',
      ttsVoice: 'nova',
      ttsApiKey: 'sk-stored',
    });
  });

  it("chooses the first provider's first model and voice, and saves all three, from nothing", async () => {
    kit.record = emptyVoice();
    const user = userEvent.setup();
    await renderSection();

    await user.click(emptyDropdowns()[0]);
    await user.click(screen.getByRole('button', { name: /OpenAI TTS/ }));

    expect(screen.getByRole('button', { name: 'TTS 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Alloy' })).toBeInTheDocument();
    await waitFor(() => expect(puts()).toHaveLength(1));
    expect(putBody()).toEqual({
      value: { ttsProvider: 'openai', ttsModel: 'tts-1', ttsVoice: 'alloy', ttsApiKey: '' },
      expectedVersion: '0',
      deviceId: 'web',
    });
  });

  it('writes nothing when the provider that is already chosen is chosen again', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.click(screen.getByRole('button', { name: /OpenAI TTS/ }));
    const [, sameProviderOption] = screen.getAllByRole('button', { name: /OpenAI TTS/ });
    await user.click(sameProviderOption);

    expect(puts()).toHaveLength(0);
    expect(screen.getByText('Configured')).toBeInTheDocument();
  });

  it('writes quick successive choices one after another, so the last one wins', async () => {
    const firstWrite = deferred<unknown>();
    let writes = 0;
    kit.apiRequest.mockImplementation(async (_path, options) => {
      if (options?.method !== 'PUT') {
        return kit.record;
      }
      writes += 1;
      return writes === 1 ? firstWrite.promise : {};
    });
    const user = userEvent.setup();
    await renderSection();

    await choose(/OpenAI TTS/, /ElevenLabs/, user);
    await choose(/Turbo v2.5/, /Multilingual v2/, user);
    await waitFor(() => expect(puts()).toHaveLength(1));

    await act(async () => firstWrite.resolve({}));

    await waitFor(() => expect(puts()).toHaveLength(2));
    expect(putBody(0).value).toMatchObject({ ttsProvider: 'elevenlabs', ttsModel: 'eleven_turbo_v2_5' });
    expect(putBody(1).value).toMatchObject({ ttsProvider: 'elevenlabs', ttsModel: 'eleven_multilingual_v2' });
  });

  it('says the choice was not saved and shows what is really stored when the server refuses it', async () => {
    kit.apiRequest.mockImplementation(async (_path, options) => {
      if (options?.method === 'PUT') {
        throw new Error('rejected');
      }
      return kit.record;
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const user = userEvent.setup();
    await renderSection();

    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    await waitFor(() => expect(kit.error).toHaveBeenCalledWith('Failed to save your selection'));
    await waitFor(() => expect(screen.getByRole('button', { name: /OpenAI TTS/ })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /ElevenLabs/ })).toBeNull();
  });

  it('warns that the Seed-Audio test is slow and explains the composite Doubao credential', async () => {
    kit.record = storedVoice({
      ttsProvider: 'volcengine',
      ttsModel: 'seed-audio-1.0',
      ttsVoice: 'zh_female_vv_uranus_bigtts',
    });
    const user = userEvent.setup();
    await renderSection();
    expect(screen.getByText(/may take 1–2 minutes/)).toBeInTheDocument();

    await choose(/Seed-Audio 1.0/, /Doubao-TTS/, user);

    expect(screen.queryByText(/may take 1–2 minutes/)).toBeNull();
    expect(screen.getByText(/appid:access_token/, { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('appid:access_token')).toBeInTheDocument();
  });
});

describe('TtsGenerationSection saving the key', () => {
  beforeEach(() => {
    kit.record = storedVoice(openaiChosen);
  });

  it('saves the trimmed key with the chosen voice, the stored version and a device id', async () => {
    const user = userEvent.setup();
    await renderSection();
    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    await user.type(keyInput(), '  sk-new  ');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalledWith('API Key saved successfully'));
    expect(puts()).toHaveLength(2);
    expect(puts()[1][0]).toBe('/config/voice');
    expect(puts()[1][1]?.silent).toBe(true);
    expect(putBody(1)).toEqual({
      value: {
        sttEnabled: true,
        ttsMaxLength: 900,
        ttsProvider: 'elevenlabs',
        ttsModel: 'eleven_turbo_v2_5',
        ttsVoice: '21m00Tcm4TlvDq8ikWAM',
        ttsApiKey: 'sk-new',
      },
      expectedVersion: 'v3',
      deviceId: 'web',
    });
  });

  it('writes against the version read at save time, not the one read at load', async () => {
    const user = userEvent.setup();
    await renderSection();
    kit.record = { ...storedVoice(openaiChosen), meta: { version: 'v4' } };

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalled());
    expect(puts()).toHaveLength(1);
    expect(putBody().expectedVersion).toBe('v4');
  });

  it('shows the key as configured and clears the field once it is saved', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(screen.getByText('Configured')).toBeInTheDocument());
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('keeps the other voice settings and creates the first ones from the chosen values only', async () => {
    kit.record = emptyVoice();
    const user = userEvent.setup();
    await renderSection();
    await user.click(emptyDropdowns()[0]);
    await user.click(screen.getByRole('button', { name: /OpenAI TTS/ }));

    await user.type(keyInput(), 'sk-first');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalled());
    expect(putBody(1)).toEqual({
      value: { ttsProvider: 'openai', ttsModel: 'tts-1', ttsVoice: 'alloy', ttsApiKey: 'sk-first' },
      expectedVersion: '0',
      deviceId: 'web',
    });
  });

  it('keeps the typed key and says so when the server refuses the save', async () => {
    const user = userEvent.setup();
    kit.apiRequest.mockImplementation(async (_path, options) => {
      if (options?.method === 'PUT') {
        throw new Error('rejected');
      }
      return kit.record;
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await renderSection();

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(kit.error).toHaveBeenCalledWith('Failed to save API Key'));
    expect(kit.success).not.toHaveBeenCalled();
    expect(keyInput()).toHaveValue('sk-new');
    expect(saveButton()).toBeEnabled();
    expect(screen.queryByText('Configured')).toBeNull();
  });

  it('cannot save a blank key', async () => {
    const user = userEvent.setup();
    await renderSection();

    await user.type(keyInput(), '   ');

    expect(saveButton()).toBeDisabled();
    expect(puts()).toHaveLength(0);
  });

  it('blocks a second save while one is in flight', async () => {
    const user = userEvent.setup();
    const pending = deferred<unknown>();
    kit.apiRequest.mockImplementation(async (_path, options) =>
      options?.method === 'PUT' ? pending.promise : kit.record,
    );
    await renderSection();

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(saveButton()).toBeDisabled());
    await act(async () => pending.resolve({}));
    await waitFor(() => expect(kit.success).toHaveBeenCalledTimes(1));
  });

  it('reveals and hides the typed key', async () => {
    const user = userEvent.setup();
    await renderSection();
    expect(keyInput()).toHaveAttribute('type', 'password');

    await user.click(eyeButton());
    expect(keyInput()).toHaveAttribute('type', 'text');

    await user.click(eyeButton());
    expect(keyInput()).toHaveAttribute('type', 'password');
  });
});
