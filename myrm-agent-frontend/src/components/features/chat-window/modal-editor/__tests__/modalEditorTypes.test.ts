import { describe, it, expect } from 'vitest';
import type {
  EditorTemplate,
  ModalEditorMetrics,
  ExternalEditorBridgePayload,
  ModalEditorStoreState,
} from '../modalEditorTypes';

describe('modalEditorTypes', () => {
  it('validates modal editor domain types and structure', () => {
    const template: EditorTemplate = {
      id: 'prd-spec',
      name: 'PRD 模板',
      description: '需求文档标准模版',
      content: '# PRD 规范',
    };
    expect(template.id).toBe('prd-spec');
    expect(template.name).toBe('PRD 模板');

    const metrics: ModalEditorMetrics = {
      charCount: 250,
      wordCount: 80,
      lineCount: 12,
    };
    expect(metrics.charCount).toBe(250);
    expect(metrics.wordCount).toBe(80);
    expect(metrics.lineCount).toBe(12);

    const payload: ExternalEditorBridgePayload = {
      sessionId: 'session-100',
      content: 'Draft content for VSCode',
      editorPreference: 'vscode',
    };
    expect(payload.sessionId).toBe('session-100');
    expect(payload.editorPreference).toBe('vscode');

    const state: ModalEditorStoreState = {
      isOpen: true,
      content: 'Hello World',
      initialContent: 'Hello World',
      isPreviewOpen: true,
      isExternalEditorActive: false,
      activeTemplateId: 'prd-spec',
    };
    expect(state.isOpen).toBe(true);
    expect(state.isPreviewOpen).toBe(true);
  });
});
