/**
 * Unit tests for sessionExportService.
 *
 * [INPUT] sessionExportService, a stubbed apiRequest
 * [OUTPUT] The three calls reach their routes through the authenticated client, and a failure rejects instead of producing a made-up result.
 * [POS] src/components/features/session-export/__tests__/sessionExportService.test.ts
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { sessionExportService } from '../sessionExportService';

vi.mock('@/lib/api', () => ({ apiRequest: vi.fn() }));

const apiRequestMock = vi.mocked(apiRequest);

describe('sessionExportService', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('exports through the authenticated client with the chosen options', async () => {
    const options = { include_thinking: true, include_tool_calls: false, enable_redaction: true, theme: 'dark' as const };
    apiRequestMock.mockResolvedValueOnce({ file_name: 'a.html' });

    await sessionExportService.exportInteractiveHtml('chat-1', options);

    const [endpoint, init] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/chats/chat-1/export/interactive-html');
    expect(init).toMatchObject({ method: 'POST', body: JSON.stringify(options), silent: true });
    expect(init?.timeout).toBeGreaterThan(30_000);
  });

  it('previews the credentials of the chat by its id', async () => {
    apiRequestMock.mockResolvedValueOnce({ total_redacted: 0, has_secrets: false, details: [] });

    await sessionExportService.previewRedaction('chat-1');

    const [endpoint, init] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/chats/chat-1/export/redact-preview');
    expect(init).toMatchObject({ method: 'POST', silent: true });
  });

  it('creates the share link through the authenticated client', async () => {
    apiRequestMock.mockResolvedValueOnce({ share_url: 'https://example.test/share/t' });

    await sessionExportService.createShareLink('chat-1', { ttl_seconds: 3600, password: 'pw' });

    const [endpoint, init] = apiRequestMock.mock.calls[0];
    expect(endpoint).toBe('/chats/chat-1/export/share-link');
    expect(init).toMatchObject({ method: 'POST', body: JSON.stringify({ ttl_seconds: 3600, password: 'pw' }) });
  });

  it.each([
    ['export', () => sessionExportService.exportInteractiveHtml('chat-1', { include_thinking: true, include_tool_calls: true, enable_redaction: true, theme: 'system' })],
    ['preview', () => sessionExportService.previewRedaction('chat-1')],
    ['share link', () => sessionExportService.createShareLink('chat-1', {})],
  ])('rejects instead of fabricating a result when the %s request fails', async (_name, call) => {
    apiRequestMock.mockRejectedValueOnce(new Error('offline'));

    await expect(call()).rejects.toThrow('offline');
  });
});
