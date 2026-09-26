/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: mocked transport)
 * [OUTPUT]
 * Vitest: trunk catalog filtering, session caching, and admit denial mapping.
 * [POS]
 * Guards the trunk discovery and admission client helpers.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequestMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    data?: Record<string, unknown>;

    constructor(message: string, data?: Record<string, unknown>) {
      super(message);
      this.data = data;
    }
  },
  apiRequest: apiRequestMock,
}));

import { admitTemplateRun } from '@/services/workflowTemplates';

async function freshTrunkCatalog() {
  vi.resetModules();
  const mod = await import('@/services/workflowTemplates');
  return mod.fetchTrunkCatalog();
}

describe('fetchTrunkCatalog', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('keeps only trunk templates', async () => {
    apiRequestMock.mockResolvedValue({
      templates: [
        { templateId: 'trunk-bugfix', displayName: 'Trunk · Bugfix', isTrunk: true },
        { templateId: 'user-flow', displayName: 'User Flow', isTrunk: false },
      ],
    });
    const catalog = await freshTrunkCatalog();
    expect(catalog.map((item) => item.template_id)).toEqual(['trunk-bugfix']);
    expect(apiRequestMock).toHaveBeenCalledTimes(1);
  });

  it('fetches once per session and shares the promise', async () => {
    apiRequestMock.mockResolvedValue({ templates: [] });
    vi.resetModules();
    const mod = await import('@/services/workflowTemplates');
    const [first, second] = await Promise.all([mod.fetchTrunkCatalog(), mod.fetchTrunkCatalog()]);
    expect(first).toEqual([]);
    expect(second).toEqual([]);
    expect(apiRequestMock).toHaveBeenCalledTimes(1);
  });

  it('returns an empty list when the request fails', async () => {
    apiRequestMock.mockRejectedValue(new Error('offline'));
    await expect(freshTrunkCatalog()).resolves.toEqual([]);
  });
});

describe('admitTemplateRun', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('maps a 422 gate denial to data instead of throwing', async () => {
    const { ApiError } = await import('@/lib/api');
    // Gate denials carry their payload on `data`; the service reads it to return a result
    // instead of throwing.
    const denial = new ApiError('denied');
    denial.data = { reason_code: 'EVIDENCE_MISSING', message: 'Add more.' };
    apiRequestMock.mockRejectedValue(denial);
    const result = await admitTemplateRun('trunk-bugfix', { template_args: {} });
    expect(result).toEqual({
      admitted: false,
      template_id: 'trunk-bugfix',
      reason_code: 'EVIDENCE_MISSING',
      user_message: 'Add more.',
    });
  });

  it('rethrows non-gate errors', async () => {
    apiRequestMock.mockRejectedValue(new Error('boom'));
    await expect(admitTemplateRun('trunk-bugfix', {})).rejects.toThrow('boom');
  });

  it('invalidates the cached catalog when the template is gone', async () => {
    const { ApiError } = await import('@/lib/api');
    vi.resetModules();
    const mod = await import('@/services/workflowTemplates');
    apiRequestMock.mockResolvedValue({
      templates: [{ templateId: 'trunk-bugfix', displayName: 'Trunk · Bugfix', isTrunk: true }],
    });
    await expect(mod.fetchTrunkCatalog()).resolves.toHaveLength(1);
    expect(apiRequestMock).toHaveBeenCalledTimes(1);
    apiRequestMock.mockRejectedValue(
      new ApiError('gone', { reason_code: 'TEMPLATE_NOT_FOUND', message: 'Gone.' }),
    );
    await mod.admitTemplateRun('trunk-bugfix', {});
    await expect(mod.fetchTrunkCatalog()).resolves.toHaveLength(1);
    expect(apiRequestMock).toHaveBeenCalledTimes(2);
  });
});
