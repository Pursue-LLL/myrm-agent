import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { usePluginImportFlow } from '../usePluginImportFlow';
import { confirmResult, previewPayload } from './pluginImportTestKit';

vi.mock('next-intl', async () => {
  const kit = await import('./pluginImportTestKit');
  return { useTranslations: kit.useTranslationsStub, useLocale: () => 'en' };
});

const { fetchAgents, reloadKeys } = vi.hoisted(() => ({ fetchAgents: vi.fn(), reloadKeys: vi.fn() }));

// One snapshot for every render, like the real store's: a fresh object each time would re-create every callback.
const agentStore = { agents: [{ id: 'agent-1', name: 'Research Assistant' }], fetchAgents };
vi.mock('@/store/useAgentStore', () => ({ default: () => agentStore }));
vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));
vi.mock('@/services/config', () => ({ getConfigSyncManager: () => ({ reloadKeys }) }));

describe('usePluginImportFlow MCP server cache', () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;
  let consoleErrorSpy: { mockRestore: () => void };

  beforeEach(() => {
    vi.clearAllMocks();
    fetchAgents.mockResolvedValue(undefined);
    reloadKeys.mockResolvedValue(undefined);
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
    // A refused request logs the backend diagnostic for developers; keep the test output quiet.
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    global.fetch = originalFetch;
    consoleErrorSpy.mockRestore();
  });

  /** Uploads an archive so the hook holds a preview, then answers the confirm request with `response`. */
  async function confirmImport(response: unknown) {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => previewPayload() });
    const { result } = renderHook(() => usePluginImportFlow({ onOpenChange: vi.fn(), onImportComplete: vi.fn() }));
    await act(async () => {
      await result.current.handleFilesSelected([new File(['zip'], 'plugin.zip')]);
    });
    fetchMock.mockResolvedValueOnce(response);
    await act(async () => {
      await result.current.confirm();
    });
    return result;
  }

  it('reloads the cached MCP servers after an import that wrote servers, so the settings page lists them', async () => {
    const result = await confirmImport({ ok: true, json: async () => confirmResult({ imported_servers: 2 }) });

    expect(result.current.result?.imported_servers).toBe(2);
    expect(reloadKeys).toHaveBeenCalledExactlyOnceWith(['mcpServers']);
  });

  it('leaves the cached MCP servers alone when the import wrote none', async () => {
    const result = await confirmImport({ ok: true, json: async () => confirmResult({ imported_skills: 1 }) });

    expect(result.current.result?.imported_skills).toBe(1);
    expect(reloadKeys).not.toHaveBeenCalled();
  });

  it('leaves the cached MCP servers alone when the confirm request is refused', async () => {
    const result = await confirmImport({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'database is locked' }),
    });

    expect(result.current.result).toBeNull();
    expect(reloadKeys).not.toHaveBeenCalled();
  });
});
