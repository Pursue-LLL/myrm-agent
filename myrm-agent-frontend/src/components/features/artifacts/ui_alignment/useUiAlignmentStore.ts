/**
 * [INPUT]
 * - UiAlignmentState, UiVariantItem, VisualAnnotationItem, VisualContractItem
 *
 * [OUTPUT]
 * - useUiAlignmentStore: Global state management hook for UI visual alignment workflow
 *
 * [POS]
 * Client store for Multi-Turn UI Design Visual Alignment Workflow (Item 39 P0).
 * Strictly under 220 lines. Zero `any`.
 */

import { create } from "zustand";
import type {
  UiAlignmentState,
  UiVariantItem,
  UiVariantStyle,
  VisualAnnotationItem,
  VisualContractItem,
} from "./uiAlignmentTypes";

const INITIAL_STATE = {
  variants: [] as UiVariantItem[],
  selectedVariantId: null as string | null,
  annotations: {} as Record<string, VisualAnnotationItem[]>,
  activeContract: null as VisualContractItem | null,
  isAnnotating: false,
  isOpen: false,
  isLoading: false,
  error: null as string | null,
};

export const useUiAlignmentStore = create<UiAlignmentState>((set, get) => ({
  ...INITIAL_STATE,

  setOpen: (open: boolean) => set({ isOpen: open }),

  setAnnotating: (annotating: boolean) => set({ isAnnotating: annotating }),

  selectVariant: (variantId: string) => set({ selectedVariantId: variantId }),

  fetchVariants: async (chatId: string) => {
    if (!chatId) {
      return;
    }
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants`);
      if (!resp.ok) {
        throw new Error(`Failed to fetch variants: ${resp.status}`);
      }
      const json = await resp.json();
      const items: UiVariantItem[] = json?.data ?? [];
      set((state) => {
        const nextSelected =
          state.selectedVariantId && items.some((v) => v.variant_id === state.selectedVariantId)
            ? state.selectedVariantId
            : items[0]?.variant_id ?? null;
        return { variants: items, selectedVariantId: nextSelected, isLoading: false };
      });
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
    }
  },

  registerVariant: async (
    chatId: string,
    variant: {
      title: string;
      style_theme: UiVariantStyle;
      html_content: string;
      css_tokens?: Record<string, string>;
      description?: string;
    }
  ) => {
    if (!chatId) {
      return null;
    }
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(variant),
      });
      if (!resp.ok) {
        throw new Error(`Failed to register variant: ${resp.status}`);
      }
      const json = await resp.json();
      const created: UiVariantItem = json.data;
      set((state) => ({
        variants: [...state.variants.filter((v) => v.variant_id !== created.variant_id), created],
        selectedVariantId: created.variant_id,
        isLoading: false,
      }));
      return created;
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
      return null;
    }
  },

  fetchAnnotations: async (chatId: string, variantId: string) => {
    if (!chatId || !variantId) {
      return;
    }
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants/${variantId}/annotations`);
      if (!resp.ok) {
        throw new Error(`Failed to fetch annotations: ${resp.status}`);
      }
      const json = await resp.json();
      const items: VisualAnnotationItem[] = json?.data ?? [];
      set((state) => ({
        annotations: {
          ...state.annotations,
          [variantId]: items,
        },
      }));
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  addAnnotation: async (
    chatId: string,
    variantId: string,
    annotation: {
      x: number;
      y: number;
      width: number;
      height: number;
      comment: string;
      label?: string;
    }
  ) => {
    if (!chatId || !variantId) {
      return null;
    }
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants/${variantId}/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(annotation),
      });
      if (!resp.ok) {
        throw new Error(`Failed to add annotation: ${resp.status}`);
      }
      const json = await resp.json();
      const created: VisualAnnotationItem = json.data;
      set((state) => {
        const existing = state.annotations[variantId] ?? [];
        return {
          annotations: {
            ...state.annotations,
            [variantId]: [...existing, created],
          },
        };
      });
      return created;
    } catch (err) {
      set({ error: (err as Error).message });
      return null;
    }
  },

  finalizeContract: async (chatId: string, variantId: string) => {
    if (!chatId || !variantId) {
      return null;
    }
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_variant_id: variantId }),
      });
      if (!resp.ok) {
        throw new Error(`Failed to finalize contract: ${resp.status}`);
      }
      const json = await resp.json();
      const contract: VisualContractItem = json.data;
      set({ activeContract: contract, isLoading: false, isAnnotating: false });
      return contract;
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
      return null;
    }
  },

  fetchContract: async (chatId: string) => {
    if (!chatId) {
      return;
    }
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/ui-variants/contract`);
      if (!resp.ok) {
        throw new Error(`Failed to fetch contract: ${resp.status}`);
      }
      const json = await resp.json();
      const contract: VisualContractItem | null = json?.data ?? null;
      set({ activeContract: contract });
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  reset: () => set({ ...INITIAL_STATE }),
}));
