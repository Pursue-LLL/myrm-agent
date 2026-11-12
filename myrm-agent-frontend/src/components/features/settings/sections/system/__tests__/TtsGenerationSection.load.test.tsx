import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import TtsGenerationSection from '../TtsGenerationSection';

interface VoiceRecord {
  value: Record<string, unknown>;
  meta: { version: string };
}

interface ApiOptions {
  method?: string;
  body?: string;
  silent?: boolean;
}

const kit = vi.hoisted(() => ({
  apiRequest: vi.fn<(path: string, options?: ApiOptions) => Promise<unknown>>(),
  error: vi.fn<(text: string) => void>(),
  providers: [] as unknown[],
  providerListeners: new Set<() => void>(),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('@/lib/api', () => ({ apiRequest: kit.apiRequest }));
// A store the section subscribes to, so a test can change the provider list while the section is mounted.
vi.mock('@/store/useProviderStore', async () => {
  const { useSyncExternalStore } = await import('react');
  const subscribe = (listener: () => void) => {
    kit.providerListeners.add(listener);
    return () => {
      kit.providerListeners.delete(listener);
    };
  };
  const useProviderStore = (select: (state: { providers: unknown[] }) => unknown) =>
    select({ providers: useSyncExternalStore(subscribe, () => kit.providers) });
  return { default: useProviderStore };
});
vi.mock('@/hooks/shared/useToast', () => ({ toast: { success: vi.fn(), error: kit.error } }));
vi.mock('@/lib/utils/media', () => ({ providerHasActiveApiKey: () => false }));
// The shared failure view probes the backend on its own; only its retry hand-off matters here.
vi.mock('@/components/features/app-shell/config-load-error', () => ({
  ConfigLoadError: ({ onRetry }: { onRetry: () => void }) => (
    <button type="button" onClick={onRetry}>
      Reload settings
    </button>
  ),
}));

const unreadable = new Error('voice settings unavailable');

const storedVoice = (overrides: Record<string, unknown> = {}): VoiceRecord => ({
  value: {
    sttEnabled: true,
    ttsProvider: 'elevenlabs',
    ttsModel: 'eleven_multilingual_v2',
    ttsVoice: 'AZnzlk1XvdvUeBnXmlld',
    ttsApiKey: 'sk-stored',
    ...overrides,
  },
  meta: { version: 'v3' },
});

/** Answers each read of the stored settings in turn (the last answer repeats); an Error is a failed read. */
function answerReads(...answers: Array<VoiceRecord | Error>): void {
  let reads = 0;
  kit.apiRequest.mockImplementation(async (_path, options) => {
    if (options?.method === 'PUT') {
      return {};
    }
    const answer = answers[Math.min(reads++, answers.length - 1)];
    if (answer instanceof Error) {
      throw answer;
    }
    return answer;
  });
}

const changeProviders = (next: unknown[]) =>
  act(async () => {
    kit.providers = next;
    kit.providerListeners.forEach((notify) => notify());
  });

const puts = () => kit.apiRequest.mock.calls.filter(([, options]) => options?.method === 'PUT');
const reloadButton = () => screen.getByRole('button', { name: 'Reload settings' });
const keyInput = () => screen.getByPlaceholderText('Enter API Key');
const saveButton = () => screen.getByRole('button', { name: 'Save' });

async function renderSection() {
  const view = render(<TtsGenerationSection />);
  await act(async () => undefined);
  return view;
}

beforeEach(() => {
  vi.resetAllMocks();
  kit.providers = [];
});

describe('TtsGenerationSection while the stored settings load', () => {
  it('shows a placeholder, not the defaults, until the stored settings arrive', async () => {
    const pending = deferred<VoiceRecord>();
    kit.apiRequest.mockImplementation(() => pending.promise);
    const { container } = render(<TtsGenerationSection />);

    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3);
    expect(screen.queryByRole('button', { name: /OpenAI TTS/ })).toBeNull();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();

    await act(async () => pending.resolve(storedVoice()));

    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(0);
    expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument();
  });

  it('shows the newest answer when an older load finishes last', async () => {
    const older = deferred<VoiceRecord>();
    const newer = deferred<VoiceRecord>();
    kit.apiRequest.mockImplementationOnce(() => older.promise).mockImplementationOnce(() => newer.promise);
    render(<TtsGenerationSection />);
    // A changed provider list makes the section read the stored settings again while the first read is pending.
    await changeProviders([{ id: 'changed' }]);

    await act(async () => newer.resolve(storedVoice({ ttsProvider: 'elevenlabs', ttsApiKey: 'sk-new' })));
    await act(async () => older.resolve(storedVoice({ ttsProvider: 'volcengine', ttsApiKey: 'sk-old' })));

    expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Seed-Audio|Doubao/ })).toBeNull();
  });
});

describe('TtsGenerationSection when the stored settings cannot be read', () => {
  it('keeps the card out of reach instead of showing the defaults, and writes nothing', async () => {
    answerReads(unreadable);

    await renderSection();

    expect(reloadButton()).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /OpenAI TTS/ })).toBeNull();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
    expect(puts()).toHaveLength(0);
    // The card shows the failure itself, so the read is silent: a global notice would add a retry that cannot reach it.
    expect(kit.apiRequest).toHaveBeenCalledWith('/config/voice', { silent: true });
  });

  it('treats an answer that carries no settings as a failed read', async () => {
    kit.apiRequest.mockResolvedValue({});

    await renderSection();

    expect(reloadButton()).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter API Key')).toBeNull();
    expect(puts()).toHaveLength(0);
  });

  it('shows the stored settings once a retry reads them', async () => {
    answerReads(unreadable, storedVoice());
    const user = userEvent.setup();
    await renderSection();

    await user.click(reloadButton());

    await waitFor(() => expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Reload settings' })).toBeNull();
    expect(screen.getByText('Configured')).toBeInTheDocument();
  });

  it('keeps offering the retry while the read keeps failing', async () => {
    answerReads(unreadable);
    const user = userEvent.setup();
    await renderSection();

    await user.click(reloadButton());

    await waitFor(() => expect(kit.apiRequest).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole('button', { name: 'Reload settings' })).toBeInTheDocument();
    expect(puts()).toHaveLength(0);
  });

  it('keeps what it has already read when a later read fails', async () => {
    answerReads(storedVoice(), unreadable);
    await renderSection();

    await changeProviders([{ id: 'changed' }]);

    expect(kit.apiRequest).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: /ElevenLabs/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reload settings' })).toBeNull();
  });

  it('refuses to save the key over settings it cannot read at that moment, and keeps the typed key', async () => {
    answerReads(storedVoice({ ttsApiKey: '' }), unreadable);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const user = userEvent.setup();
    await renderSection();

    await user.type(keyInput(), 'sk-new');
    await user.click(saveButton());

    await waitFor(() => expect(kit.error).toHaveBeenCalledWith('Failed to save API Key'));
    expect(puts()).toHaveLength(0);
    expect(keyInput()).toHaveValue('sk-new');
    expect(saveButton()).toBeEnabled();
  });
});
