/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { deferred } from '@/test-utils/deferred';

// Echoes interpolation values so the tests can see which numbers reach the copy.
const t = (key: string, values?: Record<string, number | string>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => t,
}));

const apiRequestMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest: apiRequestMock,
}));

import { ApiError } from '@/lib/api';
import MeetingNotesImportCard from '../MeetingNotesImportCard';

const MINUTES = {
  success: true,
  chunk_count: 2,
  duration_seconds: 905,
  language: 'en',
  title: 'Weekly sync',
  summary: 'Agreed to ship on Friday.',
  decisions: ['Ship on Friday'],
  debate_points: [],
  risks: [],
  action_items: [
    { description: 'Cut the release', owner: null, due_hint: null },
    { description: 'Update the docs', owner: 'Mia', due_hint: 'Thursday' },
  ],
  published_wiki_paths: ['raw/Meetings/weekly-sync.md'],
  error: '',
};
const AUDIO = new File(['audio'], 'standup.mp3', { type: 'audio/mpeg' });
const fetchSpy = vi.fn();

async function uploadAudio() {
  await userEvent.upload(screen.getByTestId('meeting-notes-file-input'), AUDIO);
  await userEvent.click(screen.getByTestId('meeting-notes-upload-btn'));
}

beforeEach(() => {
  apiRequestMock.mockReset();
  fetchSpy.mockReset();
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('MeetingNotesImportCard request', () => {
  it('uploads the audio as multipart form data through the API client with no client timeout', async () => {
    apiRequestMock.mockResolvedValue(MINUTES);
    render(<MeetingNotesImportCard />);

    await uploadAudio();

    expect(apiRequestMock).toHaveBeenCalledOnce();
    const [endpoint, options] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/wiki/meeting-notes/transcribe');
    expect(options).toMatchObject({ method: 'POST', timeout: 0, silent: true });
    expect(options.body).toBeInstanceOf(FormData);
    expect((options.body as FormData).get('file')).toMatchObject({ name: 'standup.mp3' });
    expect(options.headers).toBeUndefined();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows the minutes with localized duration and placeholders for unassigned action items', async () => {
    apiRequestMock.mockResolvedValue(MINUTES);
    render(<MeetingNotesImportCard />);

    await uploadAudio();

    const result = await screen.findByTestId('meeting-notes-result');
    expect(result).toHaveTextContent('Weekly sync');
    expect(result).toHaveTextContent('meetingNotes.durationMinutes:{"minutes":15}');
    expect(screen.getByText('Cut the release (meetingNotes.tbd · meetingNotes.tbd)')).toBeInTheDocument();
    expect(screen.getByText('Update the docs (Mia · Thursday)')).toBeInTheDocument();
    expect(result).toHaveTextContent('raw/Meetings/weekly-sync.md');
  });

  it('keeps the button busy until the transcription finishes', async () => {
    const pending = deferred<typeof MINUTES>();
    apiRequestMock.mockReturnValue(pending.promise);
    render(<MeetingNotesImportCard />);

    await uploadAudio();

    const button = screen.getByTestId('meeting-notes-upload-btn');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('meetingNotes.processing');

    await act(async () => pending.resolve(MINUTES));

    expect(await screen.findByTestId('meeting-notes-result')).toBeInTheDocument();
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent('meetingNotes.uploadButton');
  });

  it('shows the reason the server gave inline', async () => {
    apiRequestMock.mockRejectedValue(new ApiError('Audio file too large (max 500 MB)', 413));
    render(<MeetingNotesImportCard />);

    await uploadAudio();

    expect(await screen.findByTestId('meeting-notes-error')).toHaveTextContent('Audio file too large (max 500 MB)');
    expect(screen.queryByTestId('meeting-notes-result')).not.toBeInTheDocument();
  });

  it('shows the localized message instead of the raw transport error', async () => {
    apiRequestMock.mockRejectedValue(new TypeError('Failed to fetch'));
    render(<MeetingNotesImportCard />);

    await uploadAudio();

    expect(await screen.findByTestId('meeting-notes-error')).toHaveTextContent('meetingNotes.error');
    expect(screen.queryByText('Failed to fetch')).not.toBeInTheDocument();
  });

  it('sends nothing until an audio file is chosen', async () => {
    render(<MeetingNotesImportCard />);

    await userEvent.click(screen.getByTestId('meeting-notes-upload-btn'));

    expect(apiRequestMock).not.toHaveBeenCalled();
  });
});
