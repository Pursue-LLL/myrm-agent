/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/modal-editor/modalEditorTypes
 * - @/components/features/chat-window/modal-editor/modalEditorEngine
 *
 * [OUTPUT]
 * - useModalEditorStore (POS: Central reactive store for fullscreen modal Markdown editor)
 *
 * [POS]
 * Central reactive dispatcher for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite.
 * Manages modal editor draft content, clean dismissal, template insertions,
 * and desktop external editor bridge synchronization.
 */

import { create } from 'zustand';
import type { ModalEditorStoreState } from './modalEditorTypes';
import {
  BUILTIN_EDITOR_TEMPLATES,
  dispatchExternalEditorEvent,
} from './modalEditorEngine';

export interface ModalEditorStoreActions {
  readonly openEditor: (initialText?: string) => void;
  readonly setContent: (text: string) => void;
  readonly insertTemplate: (templateId: string) => void;
  readonly togglePreview: (open?: boolean) => void;
  readonly openExternalEditor: (sessionId: string) => boolean;
  readonly confirmEdit: () => string;
  readonly cancelEdit: () => void;
  readonly resetStore: () => void;
}

export type ModalEditorStore = ModalEditorStoreState & ModalEditorStoreActions;

const initialState: ModalEditorStoreState = {
  isOpen: false,
  content: '',
  initialContent: '',
  isPreviewOpen: false,
  isExternalEditorActive: false,
  activeTemplateId: null,
};

export const useModalEditorStore = create<ModalEditorStore>((set, get) => ({
  ...initialState,

  openEditor: (initialText = '') => {
    set({
      isOpen: true,
      content: initialText,
      initialContent: initialText,
      isExternalEditorActive: false,
      activeTemplateId: null,
    });
  },

  setContent: (text: string) => {
    set({ content: text });
  },

  insertTemplate: (templateId: string) => {
    const template = BUILTIN_EDITOR_TEMPLATES.find((t) => t.id === templateId);
    if (!template) {
      return;
    }

    const current = get().content;
    const separator = current.trim() ? '\n\n' : '';
    set({
      content: `${current}${separator}${template.content}`,
      activeTemplateId: templateId,
    });
  },

  togglePreview: (open?: boolean) => {
    set((state) => ({
      isPreviewOpen: typeof open === 'boolean' ? open : !state.isPreviewOpen,
    }));
  },

  openExternalEditor: (sessionId: string) => {
    const content = get().content;
    const dispatched = dispatchExternalEditorEvent({
      sessionId,
      content,
      editorPreference: 'default',
    });

    if (dispatched) {
      set({ isExternalEditorActive: true });
    }
    return dispatched;
  },

  confirmEdit: () => {
    const confirmedContent = get().content;
    set({
      isOpen: false,
      initialContent: confirmedContent,
      isExternalEditorActive: false,
    });
    return confirmedContent;
  },

  cancelEdit: () => {
    const original = get().initialContent;
    set({
      isOpen: false,
      content: original,
      isExternalEditorActive: false,
    });
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
