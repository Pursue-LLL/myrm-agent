import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiRequestMock, fetchWithTimeoutMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
  fetchWithTimeoutMock: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: apiRequestMock,
  fetchWithTimeout: fetchWithTimeoutMock,
}));

import { downloadExpertPackage, ExpertExportError, previewExpertExport } from '../expertPackage';

function response(init: { ok: boolean; body?: string; blob?: Blob; disposition?: string }): Response {
  return {
    ok: init.ok,
    text: async () => init.body ?? '',
    blob: async () => init.blob ?? new Blob(['zip']),
    headers: new Headers(init.disposition ? { 'Content-Disposition': init.disposition } : {}),
  } as unknown as Response;
}

const REQUEST = {
  agentId: 'agent-1',
  applyRedactions: true,
  ignoredRedactions: { 'agents/lead.md': [1] },
  reviewDigest: 'digest-1',
};

describe('previewExpertExport', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks the server to preview one agent without a duplicate global error toast', async () => {
    apiRequestMock.mockResolvedValue({ plugin_name: 'lead' });

    await expect(previewExpertExport('agent-1')).resolves.toEqual({ plugin_name: 'lead' });

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/plugins/export/preview',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ agent_id: 'agent-1' }),
        silent: true,
        timeout: 120_000,
      }),
    );
  });
});

describe('downloadExpertPackage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends the review decisions together with the digest they were made against', async () => {
    fetchWithTimeoutMock.mockResolvedValue(response({ ok: true }));

    await downloadExpertPackage(REQUEST);

    const [path, init, timeout] = fetchWithTimeoutMock.mock.calls[0] as [string, RequestInit, number];
    expect(path).toBe('/plugins/export');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      agent_id: 'agent-1',
      apply_redactions: true,
      ignored_redactions: { 'agents/lead.md': [1] },
      review_digest: 'digest-1',
    });
    expect(timeout).toBe(120_000);
  });

  it('returns the package and the filename the server chose', async () => {
    const blob = new Blob(['zip-bytes']);
    fetchWithTimeoutMock.mockResolvedValue(
      response({ ok: true, blob, disposition: 'attachment; filename="report-lead_v1.2.0.zip"' }),
    );

    await expect(downloadExpertPackage(REQUEST)).resolves.toEqual({ blob, filename: 'report-lead_v1.2.0.zip' });
  });

  it('returns no filename when the server sends none', async () => {
    fetchWithTimeoutMock.mockResolvedValue(response({ ok: true }));

    await expect(downloadExpertPackage(REQUEST)).resolves.toMatchObject({ filename: null });
  });

  it('exposes a machine-readable code from a structured rejection', async () => {
    fetchWithTimeoutMock.mockResolvedValue(
      response({
        ok: false,
        body: JSON.stringify({ detail: { message: 'Agent changed', error_code: 'export_changed_since_preview' } }),
      }),
    );

    const error = await downloadExpertPackage(REQUEST).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ExpertExportError);
    expect(error).toMatchObject({ message: 'Agent changed', code: 'export_changed_since_preview' });
  });

  it('uses a plain string detail as the message', async () => {
    fetchWithTimeoutMock.mockResolvedValue(
      response({ ok: false, body: JSON.stringify({ detail: 'Agent not found' }) }),
    );

    const error = await downloadExpertPackage(REQUEST).catch((caught: unknown) => caught);

    expect(error).toMatchObject({ message: 'Agent not found', code: undefined });
  });

  it('falls back to the raw body when the rejection is not JSON', async () => {
    fetchWithTimeoutMock.mockResolvedValue(response({ ok: false, body: 'upstream exploded' }));

    const error = await downloadExpertPackage(REQUEST).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ExpertExportError);
    expect(error).toMatchObject({ message: 'upstream exploded' });
  });
});
