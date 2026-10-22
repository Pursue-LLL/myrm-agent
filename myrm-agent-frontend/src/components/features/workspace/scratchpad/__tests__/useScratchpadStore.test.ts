import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useScratchpadStore } from '../useScratchpadStore';

describe('useScratchpadStore', () => {
  beforeEach(() => {
    window.localStorage.clear();
    useScratchpadStore.getState().clearDraft();
    useScratchpadStore.getState().closeScratchpad();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default closed state and empty draft', () => {
    const state = useScratchpadStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.draft.title).toBe('');
    expect(state.draft.content).toBe('');
    expect(state.draft.temporaryTags).toEqual([]);
    expect(state.isPromoting).toBe(false);
    expect(state.promotionResult).toBeNull();
  });

  it('toggles open and close states', () => {
    useScratchpadStore.getState().openScratchpad();
    expect(useScratchpadStore.getState().isOpen).toBe(true);

    useScratchpadStore.getState().closeScratchpad();
    expect(useScratchpadStore.getState().isOpen).toBe(false);
  });

  it('updates title, content, tags and writes to localStorage', () => {
    useScratchpadStore.getState().setTitle('Consensus Draft');
    useScratchpadStore.getState().setContent('Distributed nodes specification');
    useScratchpadStore.getState().setTags(['distributed', 'specs']);

    const state = useScratchpadStore.getState();
    expect(state.draft.title).toBe('Consensus Draft');
    expect(state.draft.content).toBe('Distributed nodes specification');
    expect(state.draft.temporaryTags).toEqual(['distributed', 'specs']);

    const rawStored = window.localStorage.getItem('myrm:scratchpad:draft');
    expect(rawStored).toBeTruthy();
    const parsed = JSON.parse(String(rawStored));
    expect(parsed.title).toBe('Consensus Draft');
    expect(parsed.content).toBe('Distributed nodes specification');
  });

  it('clears draft and resets promotion results', () => {
    useScratchpadStore.getState().setTitle('Temporary Notes');
    useScratchpadStore.getState().clearDraft();

    const state = useScratchpadStore.getState();
    expect(state.draft.title).toBe('');
    expect(state.draft.content).toBe('');
    expect(state.promotionResult).toBeNull();
    expect(state.error).toBeNull();
  });

  it('rejects promoting empty draft', async () => {
    await expect(useScratchpadStore.getState().promoteToProject()).rejects.toThrow(
      'Cannot promote empty scratchpad'
    );
    expect(useScratchpadStore.getState().error).toBe('Cannot promote empty scratchpad');
  });

  it('successfully promotes scratchpad via backend endpoint', async () => {
    useScratchpadStore.getState().setTitle('Task Automation App');
    useScratchpadStore.getState().setContent('A tool executing shell scripts securely.');

    const mockResponse = {
      project_name: 'task-automation-app',
      target_directory: '/workspaces/task-automation-app',
      created_files: ['docs/scratchpad_origin.md', 'README.md'],
      initial_context_prompt: '<promoted_project>',
      promoted_at: '2026-10-12T19:00:00Z',
      provenance_metadata: { source: 'scratchpad' },
    };

    const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    } as Response);

    const result = await useScratchpadStore.getState().promoteToProject('custom-app-name');

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/workspace/promote',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    expect(result).toEqual(mockResponse);
    expect(useScratchpadStore.getState().promotionResult).toEqual(mockResponse);
    expect(useScratchpadStore.getState().isPromoting).toBe(false);
  });

  it('handles promotion API failure gracefully', async () => {
    useScratchpadStore.getState().setTitle('Broken Draft');
    useScratchpadStore.getState().setContent('Broken content');

    vi.spyOn(window, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => 'Internal Server Error',
    } as Response);

    await expect(useScratchpadStore.getState().promoteToProject()).rejects.toThrow(
      'Internal Server Error'
    );
    expect(useScratchpadStore.getState().error).toBe('Internal Server Error');
    expect(useScratchpadStore.getState().isPromoting).toBe(false);
  });
});
