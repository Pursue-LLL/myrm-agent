import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useUiAlignmentStore } from '../useUiAlignmentStore';
import type { UiVariantItem, VisualAnnotationItem, VisualContractItem } from '../uiAlignmentTypes';

describe('useUiAlignmentStore', () => {
  beforeEach(() => {
    useUiAlignmentStore.getState().reset();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default empty state', () => {
    const state = useUiAlignmentStore.getState();
    expect(state.variants).toEqual([]);
    expect(state.selectedVariantId).toBeNull();
    expect(state.annotations).toEqual({});
    expect(state.activeContract).toBeNull();
    expect(state.isAnnotating).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('updates isOpen and isAnnotating toggles', () => {
    useUiAlignmentStore.getState().setOpen(true);
    expect(useUiAlignmentStore.getState().isOpen).toBe(true);

    useUiAlignmentStore.getState().setAnnotating(true);
    expect(useUiAlignmentStore.getState().isAnnotating).toBe(true);

    useUiAlignmentStore.getState().selectVariant('var_123');
    expect(useUiAlignmentStore.getState().selectedVariantId).toBe('var_123');
  });

  it('fetches variants successfully and auto-selects first item if none selected', async () => {
    const mockVariants: UiVariantItem[] = [
      {
        variant_id: 'var_01',
        title: 'Modern Bento',
        style_theme: 'modern_bento',
        html_content: '<div>Bento</div>',
        css_tokens: { '--bg': '#000' },
        description: 'Bento layout',
        created_at_ms: 1000,
      },
      {
        variant_id: 'var_02',
        title: 'Minimal Dark',
        style_theme: 'minimal_dark',
        html_content: '<div>Dark</div>',
        css_tokens: {},
        description: 'Dark layout',
        created_at_ms: 2000,
      },
    ];

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: mockVariants }),
    } as unknown as Response);

    await useUiAlignmentStore.getState().fetchVariants('chat_test');
    const state = useUiAlignmentStore.getState();
    expect(state.variants).toHaveLength(2);
    expect(state.selectedVariantId).toBe('var_01');
    expect(state.isLoading).toBe(false);
  });

  it('registers a new variant and selects it', async () => {
    const newVariant: UiVariantItem = {
      variant_id: 'var_new',
      title: 'Glassmorphism Card',
      style_theme: 'glassmorphism',
      html_content: '<section>Glass</section>',
      css_tokens: {},
      description: 'Blur effect',
      created_at_ms: 3000,
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: newVariant }),
    } as unknown as Response);

    const result = await useUiAlignmentStore.getState().registerVariant('chat_test', {
      title: 'Glassmorphism Card',
      style_theme: 'glassmorphism',
      html_content: '<section>Glass</section>',
    });

    expect(result).toEqual(newVariant);
    const state = useUiAlignmentStore.getState();
    expect(state.variants).toContainEqual(newVariant);
    expect(state.selectedVariantId).toBe('var_new');
  });

  it('adds and fetches canvas annotations for variant', async () => {
    const mockAnnotation: VisualAnnotationItem = {
      annotation_id: 'anno_1',
      variant_id: 'var_01',
      x: 10,
      y: 10,
      width: 40,
      height: 20,
      comment: 'Check color contrast ratio',
      label: 'accessibility',
      created_at_ms: 4000,
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: mockAnnotation }),
    } as unknown as Response);

    const added = await useUiAlignmentStore.getState().addAnnotation('chat_test', 'var_01', {
      x: 10,
      y: 10,
      width: 40,
      height: 20,
      comment: 'Check color contrast ratio',
      label: 'accessibility',
    });

    expect(added).toEqual(mockAnnotation);
    expect(useUiAlignmentStore.getState().annotations['var_01']).toHaveLength(1);

    // Fetch annotations
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: [mockAnnotation] }),
    } as unknown as Response);

    await useUiAlignmentStore.getState().fetchAnnotations('chat_test', 'var_01');
    expect(useUiAlignmentStore.getState().annotations['var_01']).toEqual([mockAnnotation]);
  });

  it('finalizes contract and updates activeContract in store', async () => {
    const mockContract: VisualContractItem = {
      contract_id: 'vc_888',
      session_id: 'chat_test',
      approved_variant_id: 'var_01',
      style_theme: 'modern_bento',
      dom_outline: '<div>Bento</div>',
      design_tokens: { '--bg': '#000' },
      annotations_count: 1,
      enforcement_prompt: '### [VISUAL DESIGN CONTRACT ENFORCEMENT]',
      finalized_at_ms: 5000,
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ code: 0, data: mockContract }),
    } as unknown as Response);

    const finalized = await useUiAlignmentStore.getState().finalizeContract('chat_test', 'var_01');
    expect(finalized).toEqual(mockContract);
    const state = useUiAlignmentStore.getState();
    expect(state.activeContract).toEqual(mockContract);
    expect(state.isAnnotating).toBe(false);
  });
});
