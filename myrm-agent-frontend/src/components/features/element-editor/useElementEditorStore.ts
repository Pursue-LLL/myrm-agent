import { create } from 'zustand';
import {
  ArtifactVersionSnapshot,
  EditPromptCategory,
  ElementEditorMode,
  InspectorElementInfo,
} from './elementEditorTypes';
import {
  buildTargetedMicroPatchPrompt,
  createSnapshot,
  getDefaultHtmlContent,
  getDefaultSnapshots,
} from './elementEditorEngine';

interface ElementEditorState {
  mode: ElementEditorMode;
  hoveredElement: InspectorElementInfo | null;
  selectedElement: InspectorElementInfo | null;
  contentHtml: string;
  snapshots: ArtifactVersionSnapshot[];
  currentSnapshotIndex: number;
  isHistoryOpen: boolean;
  isApplyingPatch: boolean;
  lastSynthesizedPrompt: string | null;

  setMode: (mode: ElementEditorMode) => void;
  setHoveredElement: (info: InspectorElementInfo | null) => void;
  setSelectedElement: (info: InspectorElementInfo | null) => void;
  applyMicroPatch: (instruction: string, category?: EditPromptCategory) => void;
  undo: () => boolean;
  redo: () => boolean;
  rollbackToVersion: (versionNumber: number) => void;
  toggleHistoryDeck: () => void;
  resetStore: () => void;
}

export const useElementEditorStore = create<ElementEditorState>((set, get) => ({
  mode: 'inspect',
  hoveredElement: null,
  selectedElement: null,
  contentHtml: getDefaultHtmlContent(),
  snapshots: getDefaultSnapshots(),
  currentSnapshotIndex: 0,
  isHistoryOpen: false,
  isApplyingPatch: false,
  lastSynthesizedPrompt: null,

  setMode: (mode) => {
    set({
      mode,
      hoveredElement: null,
      selectedElement: mode === 'preview' ? null : get().selectedElement,
    });
  },

  setHoveredElement: (info) => {
    set({ hoveredElement: info });
  },

  setSelectedElement: (info) => {
    set({
      selectedElement: info,
      mode: info ? 'in_place_editing' : 'inspect',
    });
  },

  applyMicroPatch: (instruction, category = 'style') => {
    const { selectedElement, contentHtml, snapshots, currentSnapshotIndex } = get();
    if (!selectedElement) {
      return;
    }

    set({ isApplyingPatch: true });

    // 组装精准微补丁 Prompt
    const prompt = buildTargetedMicroPatchPrompt({
      element: selectedElement,
      instruction,
      category,
    });

    // 局部模拟应用微补丁
    let updatedHtml = contentHtml;
    if (selectedElement.tag === 'button') {
      updatedHtml = contentHtml.replace(
        'bg-indigo-600',
        'bg-gradient-to-r from-purple-600 to-indigo-600 shadow-lg'
      );
    } else if (selectedElement.tag === 'h3') {
      updatedHtml = contentHtml.replace(
        'text-base font-bold text-white',
        'text-lg font-extrabold text-indigo-300'
      );
    } else {
      updatedHtml = `${contentHtml}\n<!-- [patch: ${instruction}] -->`;
    }

    const nextVersion = snapshots.length + 1;
    const newSnapshot = createSnapshot(
      contentHtml,
      updatedHtml,
      `修改 <${selectedElement.tag}>: ${instruction}`,
      nextVersion,
      selectedElement.tag
    );

    // 丢弃当前指针之后的分支，压入新快照
    const updatedSnapshots = [
      ...snapshots.slice(0, currentSnapshotIndex + 1),
      newSnapshot,
    ];

    set({
      contentHtml: updatedHtml,
      snapshots: updatedSnapshots,
      currentSnapshotIndex: updatedSnapshots.length - 1,
      mode: 'inspect',
      selectedElement: null,
      hoveredElement: null,
      isApplyingPatch: false,
      lastSynthesizedPrompt: prompt,
    });
  },

  undo: () => {
    const { currentSnapshotIndex, snapshots } = get();
    if (currentSnapshotIndex <= 0) {
      return false;
    }
    const targetIdx = currentSnapshotIndex - 1;
    set({
      currentSnapshotIndex: targetIdx,
      contentHtml: snapshots[targetIdx].contentHtml,
      selectedElement: null,
      hoveredElement: null,
      mode: 'inspect',
    });
    return true;
  },

  redo: () => {
    const { currentSnapshotIndex, snapshots } = get();
    if (currentSnapshotIndex >= snapshots.length - 1) {
      return false;
    }
    const targetIdx = currentSnapshotIndex + 1;
    set({
      currentSnapshotIndex: targetIdx,
      contentHtml: snapshots[targetIdx].contentHtml,
      selectedElement: null,
      hoveredElement: null,
      mode: 'inspect',
    });
    return true;
  },

  rollbackToVersion: (versionNumber) => {
    const { snapshots } = get();
    const targetIdx = snapshots.findIndex((s) => s.versionNumber === versionNumber);
    if (targetIdx !== -1) {
      set({
        currentSnapshotIndex: targetIdx,
        contentHtml: snapshots[targetIdx].contentHtml,
        selectedElement: null,
        hoveredElement: null,
        mode: 'inspect',
        isHistoryOpen: false,
      });
    }
  },

  toggleHistoryDeck: () => {
    set((state) => ({ isHistoryOpen: !state.isHistoryOpen }));
  },

  resetStore: () => {
    set({
      mode: 'inspect',
      hoveredElement: null,
      selectedElement: null,
      contentHtml: getDefaultHtmlContent(),
      snapshots: getDefaultSnapshots(),
      currentSnapshotIndex: 0,
      isHistoryOpen: false,
      isApplyingPatch: false,
      lastSynthesizedPrompt: null,
    });
  },
}));
