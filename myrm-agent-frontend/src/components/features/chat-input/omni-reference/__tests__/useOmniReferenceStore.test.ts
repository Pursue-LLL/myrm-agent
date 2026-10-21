import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useOmniReferenceStore } from '../useOmniReferenceStore';
import type { OmniReferenceItem } from '../omniReferenceTypes';

describe('useOmniReferenceStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useOmniReferenceStore.setState({
      isOpen: false,
      searchQuery: '',
      selectedDimension: 'all',
      selectedIndex: 0,
      items: [],
      isLoading: false,
      error: null,
      activeSlices: {},
    });
  });

  it('opens and closes reference menu, initializing search query and selection', () => {
    const store = useOmniReferenceStore.getState();
    store.openMenu('auth');

    expect(useOmniReferenceStore.getState().isOpen).toBe(true);
    expect(useOmniReferenceStore.getState().searchQuery).toBe('auth');
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(0);

    store.closeMenu();
    expect(useOmniReferenceStore.getState().isOpen).toBe(false);
    expect(useOmniReferenceStore.getState().searchQuery).toBe('');
  });

  it('navigates through items with selectNext and selectPrev with wrap-around', () => {
    const mockItems: OmniReferenceItem[] = [
      { dimension: 'file', target_id: 'a.py', label: 'a.py' },
      { dimension: 'session', target_id: 's1', label: 'Session 1' },
      { dimension: 'artifact', target_id: 'art1', label: 'Artifact 1' },
    ];

    useOmniReferenceStore.setState({
      isOpen: true,
      items: mockItems,
      selectedIndex: 0,
    });

    const store = useOmniReferenceStore.getState();
    store.selectNext();
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(1);

    store.selectNext();
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(2);

    store.selectNext(); // wrap around
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(0);

    store.selectPrev(); // wrap around backwards
    expect(useOmniReferenceStore.getState().selectedIndex).toBe(2);
  });

  it('fetches search suggestions from api and updates items', async () => {
    const mockApiResponse = {
      data: [
        { dimension: 'task', target_id: 'task_1', label: 'Fix memory leak' },
        { dimension: 'agent', target_id: 'agent_coder', label: 'Coder Agent' },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockApiResponse,
    } as unknown as Response);

    await useOmniReferenceStore.getState().fetchSuggestions('leak', 'task');

    const state = useOmniReferenceStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.items.length).toBe(2);
    expect(state.items[0].target_id).toBe('task_1');
  });

  it('resolves bounded context slice and caches by dimension:id key', async () => {
    const mockSlice = {
      dimension: 'session' as const,
      target_id: 'sess_99',
      label: 'Prior Chat',
      content_slice: 'Summary text here',
      is_truncated: false,
      token_estimate: 15,
      provenance_uri: 'myrm://session/sess_99',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: mockSlice }),
    } as unknown as Response);

    const item: OmniReferenceItem = {
      dimension: 'session',
      target_id: 'sess_99',
      label: 'Prior Chat',
    };

    const res = await useOmniReferenceStore.getState().resolveSlice(item);
    expect(res).toEqual(mockSlice);

    // Verify cache hit (fetch should not be called again)
    const secondCall = await useOmniReferenceStore.getState().resolveSlice(item);
    expect(secondCall).toEqual(mockSlice);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});
