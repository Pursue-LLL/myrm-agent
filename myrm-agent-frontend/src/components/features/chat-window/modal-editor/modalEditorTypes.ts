/**
 * [INPUT]
 * - None (Pure domain type definitions for Pop-out Fullscreen Modal Editor & Desktop Bridge)
 *
 * [OUTPUT]
 * - EditorTemplate, ModalEditorMetrics, ExternalEditorBridgePayload, ModalEditorStoreState
 *
 * [POS]
 * Unified types for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite.
 * Supports pop-out fullscreen Markdown composing, word/line analytics,
 * template insertion, and Tauri external desktop editor bridges (Ctrl+G).
 */

export interface EditorTemplate {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly content: string;
}

export interface ModalEditorMetrics {
  readonly charCount: number;
  readonly wordCount: number;
  readonly lineCount: number;
}

export interface ExternalEditorBridgePayload {
  readonly sessionId: string;
  readonly content: string;
  readonly editorPreference?: 'default' | 'vscode' | 'typora' | 'system';
}

export interface ModalEditorStoreState {
  readonly isOpen: boolean;
  readonly content: string;
  readonly initialContent: string;
  readonly isPreviewOpen: boolean;
  readonly isExternalEditorActive: boolean;
  readonly activeTemplateId: string | null;
}
