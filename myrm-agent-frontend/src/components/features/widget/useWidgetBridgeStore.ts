/**
 * [INPUT]
 * - widgetTypes: WidgetDisplayMode, HostContextSnapshot, HostBridgeMessage, WidgetGeneratorOptions
 *
 * [OUTPUT]
 * - useWidgetBridgeStore: Zustand store managing embed widget state and IPC communication
 *
 * [POS]
 * Client state management for Embeddable Agent Widget & Host Context Bridge (Item 41 P1).
 * Strictly under 220 lines. Zero `any`.
 */

import { create } from "zustand";
import type {
  HostBridgeMessage,
  HostContextSnapshot,
  WidgetDisplayMode,
  WidgetGeneratorOptions,
} from "./widgetTypes";

interface WidgetBridgeState {
  displayMode: WidgetDisplayMode;
  isWidgetOpen: boolean;
  isGeneratorModalOpen: boolean;
  latestSnapshot: HostContextSnapshot | null;
  injectedContextPrompt: string | null;
  allowedOrigins: string[];
  generatedSnippet: string;
  isLoading: boolean;
  messageHistory: HostBridgeMessage[];

  setDisplayMode: (mode: WidgetDisplayMode) => void;
  setWidgetOpen: (open: boolean) => void;
  setGeneratorModalOpen: (open: boolean) => void;
  setLatestSnapshot: (snapshot: HostContextSnapshot | null) => void;
  setAllowedOrigins: (origins: string[]) => void;
  appendMessage: (message: HostBridgeMessage) => void;
  generateSnippet: (chatId: string, options: WidgetGeneratorOptions) => Promise<string>;
  injectHostContext: (chatId: string, snapshot: HostContextSnapshot) => Promise<boolean>;
  fetchEmbedPolicy: (chatId: string) => Promise<void>;
  resetWidget: () => void;
}

export const useWidgetBridgeStore = create<WidgetBridgeState>((set, get) => ({
  displayMode: "floating_bubble",
  isWidgetOpen: false,
  isGeneratorModalOpen: false,
  latestSnapshot: null,
  injectedContextPrompt: null,
  allowedOrigins: ["*"],
  generatedSnippet: "",
  isLoading: false,
  messageHistory: [],

  setDisplayMode: (mode: WidgetDisplayMode) => {
    set({ displayMode: mode });
  },

  setWidgetOpen: (open: boolean) => {
    set({ isWidgetOpen: open });
  },

  setGeneratorModalOpen: (open: boolean) => {
    set({ isGeneratorModalOpen: open });
  },

  setLatestSnapshot: (snapshot: HostContextSnapshot | null) => {
    set({ latestSnapshot: snapshot });
  },

  setAllowedOrigins: (origins: string[]) => {
    set({ allowedOrigins: origins });
  },

  appendMessage: (message: HostBridgeMessage) => {
    set((state) => ({
      messageHistory: [...state.messageHistory.slice(-49), message],
    }));
  },

  generateSnippet: async (chatId: string, options: WidgetGeneratorOptions): Promise<string> => {
    set({ isLoading: true });
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/embed/generate-snippet`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          base_url: options.baseUrl,
          mode: options.mode,
          theme: options.theme,
          allowed_origin: options.allowedOrigin,
        }),
      });
      if (!response.ok) {
        throw new Error(`Failed to generate snippet: ${response.statusText}`);
      }
      const json = (await response.json()) as { data: { snippet: string } };
      const snippet = json.data?.snippet || "";
      set({ generatedSnippet: snippet, isLoading: false });
      return snippet;
    } catch {
      // Fallback local snippet generator if network fails
      const cleanedBase = options.baseUrl.replace(/\/$/, "");
      const fallbackSnippet =
        `<!-- Myrm Embeddable Agent Widget -->\n` +
        `<script\n` +
        `  src="${cleanedBase}/widget/loader.js"\n` +
        `  data-chat-id="${chatId}"\n` +
        `  data-mode="${options.mode}"\n` +
        `  data-theme="${options.theme}"\n` +
        `  data-allowed-origin="${options.allowedOrigin}"\n` +
        `  async>\n` +
        `</script>`;
      set({ generatedSnippet: fallbackSnippet, isLoading: false });
      return fallbackSnippet;
    }
  },

  injectHostContext: async (chatId: string, snapshot: HostContextSnapshot): Promise<boolean> => {
    set({ isLoading: true });
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/embed/inject-context`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin: snapshot.origin,
          current_url: snapshot.currentUrl,
          page_title: snapshot.pageTitle || "",
          selected_text: snapshot.selectedText || "",
          form_fields: snapshot.formFields || {},
          user_metadata: snapshot.userMetadata || {},
        }),
      });
      if (!response.ok) {
        set({ isLoading: false });
        return false;
      }
      const json = (await response.json()) as {
        data?: { context_text: string };
      };
      if (json.data) {
        set({
          latestSnapshot: snapshot,
          injectedContextPrompt: json.data.context_text,
          isLoading: false,
        });
        return true;
      }
      set({ isLoading: false });
      return false;
    } catch {
      set({ isLoading: false });
      return false;
    }
  },

  fetchEmbedPolicy: async (chatId: string): Promise<void> => {
    try {
      const response = await fetch(`/api/v1/chats/${chatId}/embed/policy`);
      if (response.ok) {
        const json = (await response.json()) as {
          data?: { allowed_origins: string[] };
        };
        if (json.data?.allowed_origins) {
          set({ allowedOrigins: json.data.allowed_origins });
        }
      }
    } catch {
      // Ignore network errors in optional policy fetch
    }
  },

  resetWidget: () => {
    set({
      isWidgetOpen: false,
      latestSnapshot: null,
      injectedContextPrompt: null,
      messageHistory: [],
    });
  },
}));
