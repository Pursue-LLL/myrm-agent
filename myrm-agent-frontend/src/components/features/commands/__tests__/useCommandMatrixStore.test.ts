import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useCommandMatrixStore } from '../useCommandMatrixStore';
import type { CommandMatrixEntry, CapabilityHintChip } from '../commandMatrixTypes';

describe('useCommandMatrixStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useCommandMatrixStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default closed state and empty query', () => {
    const state = useCommandMatrixStore.getState();
    expect(state.isModalOpen).toBe(false);
    expect(state.searchQuery).toBe('');
    expect(state.selectedCategory).toBe('all');
    expect(state.commands).toEqual([]);
    expect(state.selectedIndex).toBe(0);
  });

  it('toggles modal open and close correctly', () => {
    useCommandMatrixStore.getState().openModal();
    expect(useCommandMatrixStore.getState().isModalOpen).toBe(true);

    useCommandMatrixStore.getState().closeModal();
    expect(useCommandMatrixStore.getState().isModalOpen).toBe(false);

    useCommandMatrixStore.getState().toggleModal();
    expect(useCommandMatrixStore.getState().isModalOpen).toBe(true);
  });

  it('updates search query and category with selected index reset', () => {
    useCommandMatrixStore.getState().setSelectedIndex(4);
    expect(useCommandMatrixStore.getState().selectedIndex).toBe(4);

    useCommandMatrixStore.getState().setSearchQuery('python');
    expect(useCommandMatrixStore.getState().searchQuery).toBe('python');
    expect(useCommandMatrixStore.getState().selectedIndex).toBe(0);

    useCommandMatrixStore.getState().setSelectedCategory('data_science');
    expect(useCommandMatrixStore.getState().selectedCategory).toBe('data_science');
  });

  it('fetches command catalog and updates store', async () => {
    const mockItems: CommandMatrixEntry[] = [
      {
        command: '/btw',
        category: 'concurrency_collaboration',
        title_zh: '旁路插话提问',
        title_en: 'Barge-in Query',
        description_zh: '临时提问不打断主任务',
        description_en: 'Ask a side question without stopping main run',
        shortcut: 'Cmd+B',
        prompt_template: '/btw ',
        tags: ['concurrency'],
        requires_running_task: true,
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { items: mockItems } }),
    });

    await useCommandMatrixStore.getState().fetchCatalog();

    const state = useCommandMatrixStore.getState();
    expect(state.commands).toHaveLength(1);
    expect(state.commands[0].command).toBe('/btw');
    expect(state.isLoading).toBe(false);
  });

  it('marks command as mastered and persists to localStorage', () => {
    useCommandMatrixStore.setState({
      suggestedChips: [
        {
          chip_id: 'chip_1',
          command: '/btw',
          label_zh: '临时插话',
          label_en: 'Barge-in',
          reason_zh: '测试原因',
          reason_en: 'Test reason',
          priority: 100,
          insert_prompt: '/btw ',
        },
      ],
    });

    useCommandMatrixStore.getState().markCommandMastered('/btw');

    const state = useCommandMatrixStore.getState();
    expect(state.masteredCommands).toContain('/btw');
    expect(state.suggestedChips).toHaveLength(0);
    expect(localStorage.getItem('myrm_mastered_commands')).toContain('/btw');
  });

  it('fetches suggested chips based on session state', async () => {
    const mockChips: CapabilityHintChip[] = [
      {
        chip_id: 'chip_bg',
        command: '/bg',
        label_zh: '转入后台',
        label_en: 'Background',
        reason_zh: '任务耗时',
        reason_en: 'Long running',
        priority: 90,
        insert_prompt: '/bg',
      },
    ];

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { chips: mockChips } }),
    });

    await useCommandMatrixStore
      .getState()
      .fetchSuggestions('session_123', 'running', 2, ['python']);

    const state = useCommandMatrixStore.getState();
    expect(state.suggestedChips).toHaveLength(1);
    expect(state.suggestedChips[0].command).toBe('/bg');
  });
});
