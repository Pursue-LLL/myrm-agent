import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useDelightShowcaseStore } from '../useDelightShowcaseStore';
import type { DelightTemplateItem } from '../delightTypes';

describe('useDelightShowcaseStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useDelightShowcaseStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const mockTemplates: DelightTemplateItem[] = [
    {
      template_id: 'tmpl_01',
      title: 'Birthday Fireworks',
      category: 'celebration',
      description: 'Matrix rain and fireworks animation',
      prompt_seed: 'Create birthday fireworks HTML',
      html_source: '<html><body>Fireworks</body></html>',
      tags: ['birthday', 'fireworks'],
      icon_name: 'cake',
      is_featured: true,
      created_at_ms: 1000,
    },
    {
      template_id: 'tmpl_02',
      title: 'Lucky Wheel',
      category: 'utility_tools',
      description: 'Dinner decision maker',
      prompt_seed: 'Create lucky wheel HTML',
      tags: ['wheel', 'decision'],
      icon_name: 'disc',
      is_featured: true,
      created_at_ms: 2000,
    },
  ];

  it('initializes with default state', () => {
    const state = useDelightShowcaseStore.getState();
    expect(state.templates).toEqual([]);
    expect(state.selectedCategory).toBe('all');
    expect(state.searchQuery).toBe('');
    expect(state.activeTemplate).toBeNull();
    expect(state.activeSandboxHtml).toBeNull();
    expect(state.activeSandboxTitle).toBeNull();
    expect(state.isGalleryOpen).toBe(false);
    expect(state.isShowcaseOpen).toBe(false);
    expect(state.isQrCodeOpen).toBe(false);
  });

  it('updates modal toggles and category / search query', () => {
    useDelightShowcaseStore.getState().setGalleryOpen(true);
    expect(useDelightShowcaseStore.getState().isGalleryOpen).toBe(true);

    useDelightShowcaseStore.getState().setSelectedCategory('celebration');
    expect(useDelightShowcaseStore.getState().selectedCategory).toBe('celebration');

    useDelightShowcaseStore.getState().setSearchQuery('cake');
    expect(useDelightShowcaseStore.getState().searchQuery).toBe('cake');

    useDelightShowcaseStore.getState().setQrCodeOpen(true);
    expect(useDelightShowcaseStore.getState().isQrCodeOpen).toBe(true);
  });

  it('handles openShowcaseWithHtml and closeShowcase lifecycle', () => {
    useDelightShowcaseStore
      .getState()
      .openShowcaseWithHtml('Demo Title', '<div>Demo HTML</div>');

    let state = useDelightShowcaseStore.getState();
    expect(state.isShowcaseOpen).toBe(true);
    expect(state.activeSandboxTitle).toBe('Demo Title');
    expect(state.activeSandboxHtml).toBe('<div>Demo HTML</div>');

    useDelightShowcaseStore.getState().closeShowcase();
    state = useDelightShowcaseStore.getState();
    expect(state.isShowcaseOpen).toBe(false);
    expect(state.activeSandboxHtml).toBeNull();
    expect(state.activeSandboxTitle).toBeNull();
  });

  it('fetches templates and updates store', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: mockTemplates }),
    } as unknown as Response);

    await useDelightShowcaseStore.getState().fetchTemplates();
    const state = useDelightShowcaseStore.getState();
    expect(state.templates).toEqual(mockTemplates);
    expect(state.isLoading).toBe(false);
  });

  it('fetches template detail by id', async () => {
    const detail = mockTemplates[0];
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: detail }),
    } as unknown as Response);

    const result = await useDelightShowcaseStore.getState().fetchTemplateDetail('tmpl_01');
    expect(result).toEqual(detail);
    expect(useDelightShowcaseStore.getState().activeTemplate).toEqual(detail);
  });

  it('validates and compiles sandbox HTML source', async () => {
    const mockVal = {
      is_valid: true,
      issues: [],
      has_canvas: true,
      has_audio: false,
      has_tailwind: true,
      compiled_html: '<!DOCTYPE html><html><body>Valid</body></html>',
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: mockVal }),
    } as unknown as Response);

    const res = await useDelightShowcaseStore
      .getState()
      .validateAndCompileSandbox('chat_1', 'Demo', '<canvas></canvas>');

    expect(res).toEqual(mockVal);
  });
});
