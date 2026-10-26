/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import HardwareCookbook from '../HardwareCookbook';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/deploy-mode', () => ({ getDeployMode: () => 'local' }));

const profile = {
  hardware_detected: true,
  available_vram_gb: 24,
  free_disk_gb: 500,
  ollama_running: true,
  recommendations: [
    {
      model_id: 'library/llama3',
      name: 'Llama 3',
      description: 'General purpose',
      req_vram_gb: 6,
      params_b: 8,
      fit_score: 90,
      fit_level: 'perfect',
      is_installed: true,
    },
  ],
};

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

const deleteCalls = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE');

describe('HardwareCookbook model removal', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === 'DELETE'
        ? { ok: true, json: async () => ({ code: 0, data: { success: true } }) }
        : { ok: true, json: async () => ({ code: 0, data: profile }) },
    );
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('removes the model only after the user confirms, naming it in the question', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    render(<HardwareCookbook onApplyModel={vi.fn()} />);

    fireEvent.click(await screen.findByTitle('delete'));

    await waitFor(() => expect(deleteCalls(fetchMock)).toHaveLength(1));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'destructive',
      description: 'confirmDelete:llama3',
      confirmText: 'delete',
    });
    const [url, init] = deleteCalls(fetchMock)[0];
    expect(url).toBe('/api/v1/integrations/hardware/ollama/models');
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ model_name: 'llama3' });
  });

  it('keeps the model when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<HardwareCookbook onApplyModel={vi.fn()} />);

    fireEvent.click(await screen.findByTitle('delete'));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(deleteCalls(fetchMock)).toHaveLength(0);
    expect(screen.getByTitle('delete')).toBeEnabled();
  });
});
