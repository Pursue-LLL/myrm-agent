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
  record: null as VoiceRecord | null,
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/lib/api', () => ({ apiRequest: kit.apiRequest }));
vi.mock('@/store/useProviderStore', () => ({
  default: (select: (state: { providers: unknown[] }) => unknown) => select({ providers: kit.providers }),
}));
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: kit.success, error: kit.error } }));
vi.mock('@/lib/utils/media', () => ({ providerHasActiveApiKey: kit.providerKeyReady }));

const storedVoice = (overrides: Record<string, unknown> = {}): VoiceRecord => ({
  value: { sttEnabled: true, ttsMaxLength: 900, ...overrides },
  meta: { version: 'v3' },
});

const puts = () => kit.apiRequest.mock.calls.filter(([, options]) => options?.method === 'PUT');
const putBody = (index = 0) => JSON.parse(String(puts()[index][1]?.body)) as Record<string, unknown>;
const keyInput = () => screen.getByPlaceholderText('Enter API Key');
const saveButton = () => screen.getByRole('button', { name: 'Save' });
const eyeButton = () => keyInput().parentElement?.querySelector('button') as HTMLElement;

async function renderSection() {
  const view = render(<TtsGenerationSection />);
  await act(async () => undefined);
  return view;
}

async function choose(current: RegExp, option: RegExp, user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: current }));
  await user.click(screen.getByRole('button', { name: option }));
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.providers = [];
  kit.record = storedVoice({ ttsApiKey: 'sk-stored' });
  kit.providerKeyReady.mockReturnValue(false);
  kit.apiRequest.mockImplementation(async (_path, options) => {
    if (options?.method === 'PUT') {
      return {};
    }
    if (kit.record) {
      return kit.record;
    }
    throw new Error('no voice settings yet');
  });
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
    kit.record = storedVoice();

    await renderSection();

    expect(screen.getByText('API Key Required')).toBeInTheDocument();
    expect(keyInput()).toBeInTheDocument();
  });

  it("counts an active key of the provider's own list as configured", async () => {
    kit.record = storedVoice();
    kit.providerKeyReady.mockReturnValue(true);

    await renderSection();

    expect(kit.providerKeyReady).toHaveBeenCalledWith(kit.providers, 'openai');
    expect(screen.getByText('Configured')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('starts from the defaults and shows no key status when nothing is stored yet', async () => {
    kit.record = null;

    await renderSection();

    expect(screen.getByRole('button', { name: /OpenAI TTS/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /TTS 1/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Alloy/ })).toBeInTheDocument();
    expect(screen.queryByText('Configured')).toBeNull();
    expect(screen.queryByText('API Key Required')).toBeNull();
    expect(keyInput()).toBeInTheDocument();
  });

  it('shows the newest answer when an older load finishes last', async () => {
    const older = deferred<VoiceRecord>();
    const newer = deferred<VoiceRecord>();
    kit.apiRequest.mockImplementationOnce(() => older.promise).mockImplementationOnce(() => newer.promise);
    const user = userEvent.setup();
    render(<TtsGenerationSection />);
    // A changed provider list makes the section read the stored settings again while the first read is pending.
    kit.providers = [{ id: 'changed' }];
    await user.click(eyeButton());

    await act(async () => newer.resolve(storedVoice({ ttsProvider: 'elevenlabs', ttsApiKey: 'sk-new' })));
    await act(async () => older.resolve(storedVoice({ ttsProvider: 'volcengine', ttsApiKey: 'sk-old' })));

    expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Seed-Audio|Doubao/ })).toBeNull();
  });

  it.each([
    ['volcengine', 'tts-1', /Seed-Audio 1.0/],
    ['elevenlabs', 'tts-1', /Turbo v2.5/],
    ['openai', 'tts-1-hd', /TTS 1 HD/],
  ])('shows %s with the stored model %s as %s', async (ttsProvider, ttsModel, label) => {
    kit.record = storedVoice({ ttsProvider, ttsModel });

    await renderSection();

    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
  });
});

describe('TtsGenerationSection choices', () => {
  it("switches to the new provider's first model and voice", async () => {
    const user = userEvent.setup();
    await renderSection();

    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    expect(screen.getByRole('button', { name: /Turbo v2.5/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Rachel/ })).toBeInTheDocument();
  });

  it('warns that the Seed-Audio test is slow and explains the composite Doubao credential', async () => {
    kit.record = storedVoice({ ttsProvider: 'volcengine', ttsModel: 'seed-audio-1.0' });
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
  it('saves the trimmed key with the chosen voice, the stored version and a device id', async () => {
    kit.record = storedVoice();
    const user = userEvent.setup();
    await renderSection();
    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    await user.type(keyInput(), '  sk-new  ');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalledWith('API Key saved successfully'));
    expect(puts()).toHaveLength(1);
    expect(puts()[0][0]).toBe('/config/voice');
    expect(puts()[0][1]?.silent).toBe(true);
    expect(putBody()).toEqual({
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
    kit.record = storedVoice();
    const user = userEvent.setup();
    await renderSection();
    kit.record = { ...storedVoice(), meta: { version: 'v4' } };

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalled());
    expect(putBody().expectedVersion).toBe('v4');
  });

  it('shows the key as configured and clears the field once it is saved', async () => {
    const user = userEvent.setup();
    kit.record = storedVoice();
    await renderSection();

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(screen.getByText('Configured')).toBeInTheDocument());
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
  });

  it('forgets the typed key once it has been saved', async () => {
    const user = userEvent.setup();
    kit.record = storedVoice();
    await renderSection();
    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());
    await waitFor(() => expect(kit.success).toHaveBeenCalled());

    // A changed provider list makes the section read the stored settings again.
    kit.providers = [{ id: 'reloaded' }];
    await choose(/OpenAI TTS/, /ElevenLabs/, user);

    await waitFor(() => expect(keyInput()).toHaveValue(''));
  });

  it('creates the first voice settings from defaults when none are stored', async () => {
    kit.record = null;
    const user = userEvent.setup();
    await renderSection();

    await user.type(keyInput(), 'sk-first');
    await user.click(saveButton());

    await waitFor(() => expect(kit.success).toHaveBeenCalled());
    const body = putBody();
    expect(body).not.toHaveProperty('expectedVersion');
    expect(body.deviceId).toBe('web');
    expect(body.value).toMatchObject({
      sttEnabled: false,
      ttsMode: 'off',
      ttsMaxLength: 4000,
      ttsSummaryEnabled: true,
      ttsSummaryThreshold: 1500,
      ttsProvider: 'openai',
      ttsModel: 'tts-1',
      ttsVoice: 'alloy',
      ttsApiKey: 'sk-first',
    });
  });

  it('keeps the typed key and says so when the server refuses the save', async () => {
    const user = userEvent.setup();
    kit.apiRequest.mockImplementation(async (_path, options) => {
      if (options?.method === 'PUT') {
        throw new Error('rejected');
      }
      return storedVoice();
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
    kit.record = storedVoice();
    await renderSection();

    await user.type(keyInput(), '   ');

    expect(saveButton()).toBeDisabled();
    expect(puts()).toHaveLength(0);
  });

  it('blocks a second save while one is in flight', async () => {
    const user = userEvent.setup();
    kit.record = storedVoice();
    const pending = deferred<unknown>();
    kit.apiRequest.mockImplementation(async (_path, options) =>
      options?.method === 'PUT' ? pending.promise : storedVoice(),
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
    kit.record = storedVoice();
    await renderSection();
    expect(keyInput()).toHaveAttribute('type', 'password');

    await user.click(eyeButton());
    expect(keyInput()).toHaveAttribute('type', 'text');

    await user.click(eyeButton());
    expect(keyInput()).toHaveAttribute('type', 'password');
  });
});
