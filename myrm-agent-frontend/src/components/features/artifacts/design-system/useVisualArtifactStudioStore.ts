import { create } from 'zustand';
import type {
  DesignSystemSpec,
  PublicShareRecord,
  SelectedElementMeta,
  VisualArtifactStudioState,
} from './designSpecTypes';
import { MINIMAL_B2B_SPEC } from './designSpecParser';

function generateBackfillPrompt(element: SelectedElementMeta, spec: DesignSystemSpec): string {
  const contentBrief = element.textContent.slice(0, 30);
  return `针对当前设计规范 [${spec.name}] 进行局部微调：
- 目标元素定位: ${element.selectorPath} (${element.tagName})
- 当前文本内容: "${contentBrief}"
- 盒模型尺寸: ${element.boundingBox.width}px × ${element.boundingBox.height}px
- 修改意图: 请优化此组件在 ${spec.tokens.geometry.borderRadius} 圆角下的间距与视觉层级，并确保文字与背景对比度符合规范。`;
}

export const useVisualArtifactStudioStore = create<VisualArtifactStudioState>(
  (set, get) => ({
    currentArtifactId: 'art_landing_demo_01',
    activeSpec: MINIMAL_B2B_SPEC,
    isInspectMode: false,
    hoveredElement: null,
    selectedElement: null,
    promptBackfillText: '',
    isShareModalOpen: false,
    publicShares: [],

    setActiveSpec: (spec: DesignSystemSpec) => {
      set({ activeSpec: spec });
      const currentSelected = get().selectedElement;
      if (currentSelected) {
        set({
          promptBackfillText: generateBackfillPrompt(currentSelected, spec),
        });
      }
    },

    toggleInspectMode: (enabled?: boolean) => {
      set((state) => ({
        isInspectMode: enabled !== undefined ? enabled : !state.isInspectMode,
        hoveredElement: null,
      }));
    },

    setHoveredElement: (element: SelectedElementMeta | null) => {
      set({ hoveredElement: element });
    },

    selectElement: (element: SelectedElementMeta | null) => {
      const spec = get().activeSpec;
      if (element) {
        const prompt = generateBackfillPrompt(element, spec);
        set({
          selectedElement: element,
          promptBackfillText: prompt,
        });
      } else {
        set({
          selectedElement: null,
          promptBackfillText: '',
        });
      }
    },

    clearSelection: () => {
      set({
        selectedElement: null,
        hoveredElement: null,
        promptBackfillText: '',
      });
    },

    setPromptBackfillText: (text: string) => {
      set({ promptBackfillText: text });
    },

    openShareModal: () => {
      set({ isShareModalOpen: true });
    },

    closeShareModal: () => {
      set({ isShareModalOpen: false });
    },

    generatePublicShare: (
      artifactId: string,
      durationHours: number | null,
      watermarkText = '由 Myrmidon AI 遵循 DESIGN.md 规范自动构建'
    ): PublicShareRecord => {
      const shareId = `share_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      const now = new Date();
      let expiresAt: string | null = null;

      if (durationHours !== null && durationHours > 0) {
        const expDate = new Date(now.getTime() + durationHours * 3600 * 1000);
        expiresAt = expDate.toISOString();
      }

      const newRecord: PublicShareRecord = {
        shareId,
        artifactId,
        publicUrl: `https://share.myrm.io/s/${shareId}`,
        createdAt: now.toISOString(),
        expiresAt,
        watermarkText,
        isRevoked: false,
        visitCount: 0,
      };

      set((state) => ({
        publicShares: [newRecord, ...state.publicShares],
      }));

      return newRecord;
    },

    revokePublicShare: (shareId: string) => {
      set((state) => ({
        publicShares: state.publicShares.map((rec) => {
          if (rec.shareId === shareId) {
            return { ...rec, isRevoked: true };
          }
          return rec;
        }),
      }));
    },

    resetStudioState: () => {
      set({
        currentArtifactId: 'art_landing_demo_01',
        activeSpec: MINIMAL_B2B_SPEC,
        isInspectMode: false,
        hoveredElement: null,
        selectedElement: null,
        promptBackfillText: '',
        isShareModalOpen: false,
        publicShares: [],
      });
    },
  })
);
