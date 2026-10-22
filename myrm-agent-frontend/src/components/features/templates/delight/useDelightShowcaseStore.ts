/**
 * [INPUT]
 * - DelightCategory, DelightTemplateItem, DelightShowcaseState, SandboxValidationResultItem
 *
 * [OUTPUT]
 * - useDelightShowcaseStore: Zustand hook governing hobbyist delight templates & single-file sandbox
 *
 * [POS]
 * Client store for Zero-Code Hobbyist Delight & Single-File Sandbox (Item 40 P0).
 * Strictly under 220 lines. Zero `any`.
 */

import { create } from "zustand";
import type {
  DelightCategory,
  DelightShowcaseState,
  DelightTemplateItem,
  SandboxValidationResultItem,
} from "./delightTypes";

const INITIAL_STATE = {
  templates: [] as DelightTemplateItem[],
  selectedCategory: "all" as DelightCategory,
  searchQuery: "",
  activeTemplate: null as DelightTemplateItem | null,
  activeSandboxHtml: null as string | null,
  activeSandboxTitle: null as string | null,
  isGalleryOpen: false,
  isShowcaseOpen: false,
  isQrCodeOpen: false,
  isLoading: false,
  error: null as string | null,
};

export const useDelightShowcaseStore = create<DelightShowcaseState>((set, get) => ({
  ...INITIAL_STATE,

  setGalleryOpen: (open: boolean) => set({ isGalleryOpen: open }),

  setShowcaseOpen: (open: boolean) => set({ isShowcaseOpen: open }),

  setQrCodeOpen: (open: boolean) => set({ isQrCodeOpen: open }),

  setSelectedCategory: (category: DelightCategory) => set({ selectedCategory: category }),

  setSearchQuery: (query: string) => set({ searchQuery: query }),

  setActiveTemplate: (template: DelightTemplateItem | null) => set({ activeTemplate: template }),

  openShowcaseWithHtml: (title: string, html: string) =>
    set({
      activeSandboxTitle: title,
      activeSandboxHtml: html,
      isShowcaseOpen: true,
    }),

  closeShowcase: () =>
    set({
      isShowcaseOpen: false,
      isQrCodeOpen: false,
      activeSandboxHtml: null,
      activeSandboxTitle: null,
    }),

  fetchTemplates: async () => {
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch("/api/v1/chats/delight-templates");
      if (!resp.ok) {
        throw new Error(`Failed to fetch delight templates: ${resp.status}`);
      }
      const json = await resp.json();
      const items: DelightTemplateItem[] = json?.data ?? [];
      set({ templates: items, isLoading: false });
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
    }
  },

  fetchTemplateDetail: async (templateId: string) => {
    if (!templateId) {
      return null;
    }
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch(`/api/v1/chats/delight-templates/${templateId}`);
      if (!resp.ok) {
        throw new Error(`Failed to fetch template detail: ${resp.status}`);
      }
      const json = await resp.json();
      const detail: DelightTemplateItem = json.data;
      set({ activeTemplate: detail, isLoading: false });
      return detail;
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
      return null;
    }
  },

  validateAndCompileSandbox: async (
    chatId: string,
    title: string,
    htmlSource: string
  ): Promise<SandboxValidationResultItem | null> => {
    if (!htmlSource.trim()) {
      return null;
    }
    try {
      const resp = await fetch(`/api/v1/chats/${chatId}/delight-sandbox/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ html_source: htmlSource, title }),
      });
      if (!resp.ok) {
        throw new Error(`Failed to validate sandbox: ${resp.status}`);
      }
      const json = await resp.json();
      return json.data as SandboxValidationResultItem;
    } catch (err) {
      set({ error: (err as Error).message });
      return null;
    }
  },

  reset: () => set({ ...INITIAL_STATE }),
}));
