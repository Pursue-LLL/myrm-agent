import { create } from 'zustand';
import {
  InlineElementStyles,
  InlineEditMode,
  MutationDiffSummary,
  SelectedDomElementInfo,
  WysiwygEditorState,
  ZeroTokenCommitReport,
} from './wysiwygEditorTypes';
import {
  applyTextMutationToHtml,
  buildZeroTokenCommitReport,
} from './wysiwygEditorEngine';

export interface WysiwygEditorActions {
  loadHtml: (html: string) => void;
  toggleEditMode: (editing?: boolean) => void;
  selectElement: (element: SelectedDomElementInfo | null) => void;
  updateSelectedText: (newText: string) => void;
  updateSelectedStyle: (stylePatch: Partial<InlineElementStyles>) => void;
  commitZeroTokenSave: () => ZeroTokenCommitReport;
  discardChanges: () => void;
  reset: () => void;
}

export type WysiwygEditorStore = WysiwygEditorState &
  WysiwygEditorActions & {
    version: number;
  };

const initialState: WysiwygEditorState & { version: number } = {
  mode: 'preview',
  originalHtml: '',
  currentHtml: '',
  selectedElement: null,
  pendingMutations: [],
  lastCommitReport: null,
  version: 1,
};

export const useWysiwygEditorStore = create<WysiwygEditorStore>(
  (set, get) => ({
    ...initialState,

    loadHtml: (html: string) => {
      set({
        originalHtml: html,
        currentHtml: html,
        mode: 'preview',
        selectedElement: null,
        pendingMutations: [],
        lastCommitReport: null,
        version: 1,
      });
    },

    toggleEditMode: (editing) => {
      const currentMode = get().mode;
      const targetMode: InlineEditMode =
        typeof editing === 'boolean'
          ? editing
            ? 'editing'
            : 'preview'
          : currentMode === 'editing'
            ? 'preview'
            : 'editing';

      set({
        mode: targetMode,
        selectedElement: targetMode === 'preview' ? null : get().selectedElement,
      });
    },

    selectElement: (element) => {
      set({ selectedElement: element });
    },

    updateSelectedText: (newText) => {
      const { selectedElement, currentHtml, pendingMutations } = get();
      if (!selectedElement) {
        return;
      }

      const oldText = selectedElement.textContent;
      if (oldText === newText) {
        return;
      }

      const updatedHtml = applyTextMutationToHtml(currentHtml, oldText, newText);

      const mutation: MutationDiffSummary = {
        id: `mut-text-${Date.now()}`,
        timestamp: Date.now(),
        selector: selectedElement.selector,
        changeType: 'text',
        originalValue: oldText,
        newValue: newText,
      };

      set({
        currentHtml: updatedHtml,
        selectedElement: {
          ...selectedElement,
          textContent: newText,
        },
        pendingMutations: [...pendingMutations, mutation],
      });
    },

    updateSelectedStyle: (stylePatch) => {
      const { selectedElement, pendingMutations } = get();
      if (!selectedElement) {
        return;
      }

      const updatedStyles: InlineElementStyles = {
        ...selectedElement.styles,
        ...stylePatch,
      };

      const mutation: MutationDiffSummary = {
        id: `mut-style-${Date.now()}`,
        timestamp: Date.now(),
        selector: selectedElement.selector,
        changeType: 'style',
        originalValue: JSON.stringify(selectedElement.styles),
        newValue: JSON.stringify(updatedStyles),
      };

      set({
        selectedElement: {
          ...selectedElement,
          styles: updatedStyles,
        },
        pendingMutations: [...pendingMutations, mutation],
      });
    },

    commitZeroTokenSave: () => {
      const { currentHtml, pendingMutations, version } = get();

      set({ mode: 'saving' });

      const nextVersion = version + 1;
      const report = buildZeroTokenCommitReport(
        pendingMutations,
        nextVersion,
        currentHtml.length
      );

      set({
        originalHtml: currentHtml,
        mode: 'preview',
        selectedElement: null,
        pendingMutations: [],
        lastCommitReport: report,
        version: nextVersion,
      });

      return report;
    },

    discardChanges: () => {
      const { originalHtml } = get();
      set({
        currentHtml: originalHtml,
        selectedElement: null,
        pendingMutations: [],
        mode: 'preview',
      });
    },

    reset: () => {
      set(initialState);
    },
  })
);
