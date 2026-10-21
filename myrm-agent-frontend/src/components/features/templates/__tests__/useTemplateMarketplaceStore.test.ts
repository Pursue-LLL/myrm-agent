import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useTemplateMarketplaceStore } from '../useTemplateMarketplaceStore';
import type { AgentTemplateItem } from '../templateTypes';

describe('useTemplateMarketplaceStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useTemplateMarketplaceStore.setState({
      templates: [],
      isLoading: false,
      error: null,
      searchQuery: '',
      selectedCategory: 'all',
      activeTemplateForClone: null,
      isCloneWorkbenchOpen: false,
      isCloning: false,
      cloneError: null,
    });
  });

  it('fetches and enriches prebuilt agent templates successfully', async () => {
    const mockApiResponse = {
      data: [
        {
          id: 'frontend_development_expert',
          name: '前端开发专家',
          description: '精通 React 与现代化 Web 开发',
          agent_type: 'individual',
          category: 'engineering',
          enabled_builtin_tools: ['read_file', 'write_file'],
          use_cases: ['Web 前端开发', '页面重构'],
        },
      ],
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockApiResponse,
    } as unknown as Response);

    await useTemplateMarketplaceStore.getState().fetchTemplates();

    const state = useTemplateMarketplaceStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.templates.length).toBe(1);
    expect(state.templates[0].id).toBe('frontend_development_expert');
    expect(state.templates[0].category).toBe('engineering');
    expect(state.templates[0].wiki_blueprint).toContain('architecture/');
  });

  it('handles fetch failure and records error state', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    } as unknown as Response);

    await useTemplateMarketplaceStore.getState().fetchTemplates();

    const state = useTemplateMarketplaceStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toContain('HTTP 500');
    expect(state.templates.length).toBe(0);
  });

  it('filters templates via searchQuery and category setters', () => {
    const store = useTemplateMarketplaceStore.getState();
    store.setSearchQuery('react');
    expect(useTemplateMarketplaceStore.getState().searchQuery).toBe('react');

    store.setSelectedCategory('engineering');
    expect(useTemplateMarketplaceStore.getState().selectedCategory).toBe('engineering');
  });

  it('opens and closes clone workbench modal', () => {
    const mockTemplate: AgentTemplateItem = {
      id: 'ui_design_expert',
      name: 'UI 设计师',
      agent_type: 'individual',
      category: 'engineering',
    };

    const store = useTemplateMarketplaceStore.getState();
    store.openCloneWorkbench(mockTemplate);

    expect(useTemplateMarketplaceStore.getState().isCloneWorkbenchOpen).toBe(true);
    expect(useTemplateMarketplaceStore.getState().activeTemplateForClone?.id).toBe('ui_design_expert');

    store.closeCloneWorkbench();
    expect(useTemplateMarketplaceStore.getState().isCloneWorkbenchOpen).toBe(false);
    expect(useTemplateMarketplaceStore.getState().activeTemplateForClone).toBeNull();
  });

  it('instantiates template and resets clone workbench on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        data: { id: 'new_agent_999', name: 'My UI Agent' },
      }),
    } as unknown as Response);

    const store = useTemplateMarketplaceStore.getState();
    store.openCloneWorkbench({
      id: 'ui_design_expert',
      name: 'UI 设计师',
      agent_type: 'individual',
      category: 'engineering',
    });

    const res = await store.instantiateTemplate({
      templateId: 'ui_design_expert',
      customName: 'My UI Agent',
      initWikiBlueprint: true,
    });

    expect(res).toEqual({ id: 'new_agent_999', name: 'My UI Agent' });
    expect(useTemplateMarketplaceStore.getState().isCloneWorkbenchOpen).toBe(false);
    expect(useTemplateMarketplaceStore.getState().isCloning).toBe(false);
  });
});
