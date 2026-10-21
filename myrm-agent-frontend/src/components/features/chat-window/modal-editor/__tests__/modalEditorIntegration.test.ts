import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  calculateEditorMetrics,
  BUILTIN_EDITOR_TEMPLATES,
  dispatchExternalEditorEvent,
} from '../modalEditorEngine';
import { useModalEditorStore } from '../useModalEditorStore';

describe('modalEditorIntegration', () => {
  beforeEach(() => {
    useModalEditorStore.getState().resetStore();
  });

  it('completes end-to-end composing lifecycle from drafting to confirmation', () => {
    // 1. User has short draft in chat input, triggers popout (Ctrl+G)
    const initialDraft = '我要做一个全屏公文编辑器';
    useModalEditorStore.getState().openEditor(initialDraft);

    expect(useModalEditorStore.getState().isOpen).toBe(true);
    expect(useModalEditorStore.getState().content).toBe(initialDraft);

    // 2. Insert PRD template
    useModalEditorStore.getState().insertTemplate('prd-spec');
    const enrichedContent = useModalEditorStore.getState().content;
    expect(enrichedContent).toContain(initialDraft);
    expect(enrichedContent).toContain('业务背景与目标');

    // 3. Telemetry metrics calculation
    const metrics = calculateEditorMetrics(enrichedContent);
    expect(metrics.charCount).toBeGreaterThan(100);
    expect(metrics.lineCount).toBeGreaterThan(10);

    // 4. Toggle side-by-side preview
    useModalEditorStore.getState().togglePreview(true);
    expect(useModalEditorStore.getState().isPreviewOpen).toBe(true);

    // 5. User confirms and text is passed back to input box
    const finalResult = useModalEditorStore.getState().confirmEdit();
    expect(finalResult).toBe(enrichedContent);
    expect(useModalEditorStore.getState().isOpen).toBe(false);
  });

  it('verifies clean dismissal safety without polluting initial text', () => {
    const safeContent = '原有的重要需求草案';
    useModalEditorStore.getState().openEditor(safeContent);

    // User modifies or messes up content
    useModalEditorStore.getState().setContent('破坏性的错误输入');
    expect(useModalEditorStore.getState().content).toBe('破坏性的错误输入');

    // User presses Esc or clicks Cancel
    useModalEditorStore.getState().cancelEdit();

    expect(useModalEditorStore.getState().isOpen).toBe(false);
    expect(useModalEditorStore.getState().content).toBe(safeContent);
  });

  it('verifies desktop external editor bridge event propagation', () => {
    const listener = vi.fn();
    window.addEventListener('myrm:open-external-editor', listener);

    useModalEditorStore.getState().openEditor('# 外部编辑器草稿');
    const ok = useModalEditorStore.getState().openExternalEditor('chat-bridge-1');

    expect(ok).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);

    const event = listener.mock.calls[0][0] as CustomEvent;
    expect(event.detail.sessionId).toBe('chat-bridge-1');
    expect(event.detail.content).toBe('# 外部编辑器草稿');

    window.removeEventListener('myrm:open-external-editor', listener);
  });
});
