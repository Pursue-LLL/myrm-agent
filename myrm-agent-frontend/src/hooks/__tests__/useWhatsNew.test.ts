import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

let mockIsTauri = false;
let mockVersion = '1.0.0';
let mockVersionRejects = false;

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

vi.mock('@tauri-apps/api/app', () => ({
  getVersion: () =>
    mockVersionRejects
      ? Promise.reject(new Error('no tauri'))
      : Promise.resolve(mockVersion),
}));

describe('useWhatsNew', () => {
  beforeEach(() => {
    mockIsTauri = false;
    mockVersion = '1.0.0';
    mockVersionRejects = false;
    localStorage.clear();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  async function loadHook() {
    const mod = await import('@/hooks/useWhatsNew');
    return mod.useWhatsNew;
  }

  it('returns idle state when not in Tauri runtime', async () => {
    mockIsTauri = false;
    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    expect(result.current.visible).toBe(false);
    expect(result.current.release).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it('returns idle state when Tauri getVersion fails', async () => {
    mockIsTauri = true;
    mockVersionRejects = true;
    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
  });

  it('does not show modal when lastSeen matches current version', async () => {
    mockIsTauri = true;
    mockVersion = '1.0.0';
    localStorage.setItem('myrm-whats-new-last-seen-version', '1.0.0');
    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
  });

  it('shows modal when version changes and fetch succeeds', async () => {
    mockIsTauri = true;
    mockVersion = '2.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          body: '## New Feature\n- Added something',
          published_at: '2025-01-01T00:00:00Z',
          html_url: 'https://github.com/test/releases/tag/v2.0.0',
        }),
        { status: 200 },
      ),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.visible).toBe(true));
    expect(result.current.release).not.toBeNull();
    expect(result.current.release?.version).toBe('2.0.0');
    expect(result.current.release?.body).toContain('New Feature');
    fetchSpy.mockRestore();
  });

  it('does not show modal when fetch returns empty body', async () => {
    mockIsTauri = true;
    mockVersion = '3.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ body: '', published_at: '', html_url: '' }),
        { status: 200 },
      ),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    expect(localStorage.getItem('myrm-whats-new-last-seen-version')).toBe('3.0.0');
    fetchSpy.mockRestore();
  });

  it('does not show modal when fetch fails (404)', async () => {
    mockIsTauri = true;
    mockVersion = '4.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('Not Found', { status: 404 }),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    fetchSpy.mockRestore();
  });

  it('does not show modal when fetch throws (network error)', async () => {
    mockIsTauri = true;
    mockVersion = '4.1.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(
      new Error('Network error'),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    fetchSpy.mockRestore();
  });

  it('handles non-JSON response gracefully', async () => {
    mockIsTauri = true;
    mockVersion = '6.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>CDN Error</html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    fetchSpy.mockRestore();
  });

  it('handles missing body field in JSON response', async () => {
    mockIsTauri = true;
    mockVersion = '7.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ tag_name: 'v7.0.0' }), { status: 200 }),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    fetchSpy.mockRestore();
  });

  it('handles whitespace-only body as empty', async () => {
    mockIsTauri = true;
    mockVersion = '8.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ body: '   \n  \n  ', published_at: '', html_url: '' }),
        { status: 200 },
      ),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.visible).toBe(false);
    expect(localStorage.getItem('myrm-whats-new-last-seen-version')).toBe('8.0.0');
    fetchSpy.mockRestore();
  });

  it('dismiss saves version to localStorage', async () => {
    mockIsTauri = true;
    mockVersion = '5.0.0';
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          body: 'Release notes',
          published_at: '2025-01-01T00:00:00Z',
          html_url: 'https://github.com/test/releases/tag/v5.0.0',
        }),
        { status: 200 },
      ),
    );

    const useWhatsNew = await loadHook();
    const { result } = renderHook(() => useWhatsNew());
    await waitFor(() => expect(result.current.visible).toBe(true));

    act(() => {
      result.current.dismiss();
    });

    await waitFor(() => expect(result.current.visible).toBe(false));
    expect(localStorage.getItem('myrm-whats-new-last-seen-version')).toBe('5.0.0');
    fetchSpy.mockRestore();
  });
});
