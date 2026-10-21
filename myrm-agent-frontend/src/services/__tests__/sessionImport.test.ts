import { describe, expect, it, vi, beforeEach } from 'vitest';
import { apiRequest } from '@/lib/api';
import { importTranscriptJson, importTranscriptFile, type ImportTranscriptResult } from '@/services/sessionImport';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = apiRequest as unknown as ReturnType<typeof vi.fn>;

describe('sessionImport services', () => {
  const mockResult: ImportTranscriptResult = {
    ok: true,
    chat_id: 'chat-import-123',
    title: 'Migrated Hermes Session',
    source_platform: 'hermes',
    turns_count: 4,
    raw_tokens_estimate: 10000,
    clean_tokens_estimate: 1500,
    reduction_ratio: 0.85,
  };

  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('importTranscriptJson sends POST to /chats/import-transcript with correct body', async () => {
    apiRequestMock.mockResolvedValue(mockResult);

    const result = await importTranscriptJson({
      raw_content: '{"role": "user", "content": "hi"}',
      source_hint: 'hermes',
    });

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/chats/import-transcript',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          raw_content: '{"role": "user", "content": "hi"}',
          source_hint: 'hermes',
        }),
      }),
    );
    expect(result).toEqual(mockResult);
    expect(result.reduction_ratio).toBe(0.85);
  });

  it('importTranscriptFile sends multipart FormData to /chats/import-transcript/file', async () => {
    apiRequestMock.mockResolvedValue(mockResult);

    const file = new File(['{"role": "user", "content": "hi"}'], 'transcript.jsonl', {
      type: 'text/plain',
    });

    const result = await importTranscriptFile(file, {
      source_hint: 'hermes',
      title_override: 'Custom Title',
    });

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/chats/import-transcript/file',
      expect.objectContaining({
        method: 'POST',
      }),
    );

    const callArgs = apiRequestMock.mock.calls[0];
    const formData = callArgs[1]?.body as unknown as FormData;
    expect(formData.get('source_hint')).toBe('hermes');
    expect(formData.get('title_override')).toBe('Custom Title');
    expect(result.chat_id).toBe('chat-import-123');
    expect(result.turns_count).toBe(4);
  });

  it('importTranscriptFile propagates error when apiRequest fails', async () => {
    apiRequestMock.mockRejectedValue(new Error('Invalid transcript format'));

    const file = new File(['corrupt data'], 'transcript.json', { type: 'text/plain' });

    await expect(importTranscriptFile(file)).rejects.toThrow('Invalid transcript format');
  });
});
