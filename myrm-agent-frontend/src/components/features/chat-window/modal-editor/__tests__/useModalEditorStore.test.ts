import { describe, it, expect, beforeEach } from 'vitest';
import { useModalEditorStore } from '../useModalEditorStore';

describe('useModalEditorStore', () => {
  beforeEach(() => {
    useModalEditorStore.getState().resetStore();
  });

  it('initializes with default closed state', () => {
    const state = useModalEditorStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.content).toBe('');
    expect(state.initialContent).toBe('');
    expect(state.isPreviewOpen).toBe(false);
    expect(state.isExternalEditorActive).toBe(false);
    expect(state.activeTemplateId).toBeNull();
  });

  it('opens editor with initial text and sets content', () => {
    useModalEditorStore.getState().openEditor('Initial prompt text');
    expect(useModalEditorStore.getState().isOpen).toBe(true);
    expect(useModalEditorStore.getState().content).toBe('Initial prompt text');
    expect(useModalEditorStore.getState().initialContent).toBe('Initial prompt text');

    useModalEditorStore.getState().setContent('Modified text');
    expect(useModalEditorStore.getState().content).toBe('Modified text');
  });

  it('inserts template content and tracks activeTemplateId', () => {
    useModalEditorStore.getState().openEditor('Header');
    useModalEditorStore.getState().insertTemplate('prd-spec');

    const content = useModalEditorStore.getState().content;
    expect(content).toContain('Header');
    expect(content).toContain('产品需求规范 (PRD)');
    expect(useModalEditorStore.getState().activeTemplateId).toBe('prd-spec');
  });

  it('toggles preview mode', () => {
    useModalEditorStore.getState().togglePreview(true);
    expect(useModalEditorStore.getState().isPreviewOpen).toBe(true);

    useModalEditorStore.getState().togglePreview(false);
    expect(useModalEditorStore.getState().isPreviewOpen).toBe(false);

    useModalEditorStore.getState().togglePreview();
    expect(useModalEditorStore.getState().isPreviewOpen).toBe(true);
  });

  it('handles external editor bridge dispatch', () => {
    useModalEditorStore.getState().openEditor('External draft');
    const dispatched = useModalEditorStore.getState().openExternalEditor('session-qa');
    expect(dispatched).toBe(true);
    expect(useModalEditorStore.getState().isExternalEditorActive).toBe(true);
  });

  it('confirms edit and closes modal with updated content', () => {
    useModalEditorStore.getState().openEditor('Draft');
    useModalEditorStore.getState().setContent('Final Content');

    const result = useModalEditorStore.getState().confirmEdit();
    expect(result).toBe('Final Content');
    expect(useModalEditorStore.getState().isOpen).toBe(false);
    expect(useModalEditorStore.getState().initialContent).toBe('Final Content');
  });

  it('cancels edit with clean dismissal, reverting back to initial content', () => {
    useModalEditorStore.getState().openEditor('Safe Original');
    useModalEditorStore.getState().setContent('Accidental Deletion or Bad Edits');

    useModalEditorStore.getState().cancelEdit();
    expect(useModalEditorStore.getState().isOpen).toBe(false);
    expect(useModalEditorStore.getState().content).toBe('Safe Original');
  });
});
