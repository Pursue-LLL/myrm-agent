/**
 * [INPUT]
 * - create from 'zustand'
 * - UIRequestItem from '@/components/features/extension-ui/extensionUITypes'
 * - submitUIResponse, cancelUIRequest, fetchPendingUIRequests from '@/services/extensionUIService'
 *
 * [OUTPUT]
 * - useExtensionUIStore: Global state management for Extension UI prompts
 *
 * [POS]
 * Client store driving interactive modal prompts for reverse push protocol (Item 28).
 * Single file < 220 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { UIRequestItem } from '@/components/features/extension-ui/extensionUITypes';
import {
  submitUIResponse,
  cancelUIRequest,
  fetchPendingUIRequests,
} from '@/services/extensionUIService';

interface ExtensionUIState {
  chatId: string | null;
  activeRequest: UIRequestItem | null;
  queue: UIRequestItem[];
  isSubmitting: boolean;
  selectedValue: string;
  inputValue: string;
  editorValue: string;

  // Actions
  setChatId: (chatId: string | null) => void;
  enqueueRequest: (req: UIRequestItem) => void;
  setSelectedValue: (val: string) => void;
  setInputValue: (val: string) => void;
  setEditorValue: (val: string) => void;
  resolveCurrent: (customValue?: string | boolean) => Promise<boolean>;
  cancelCurrent: (reason?: string) => Promise<boolean>;
  fetchPending: (chatId: string) => Promise<void>;
  reset: () => void;
}

export const useExtensionUIStore = create<ExtensionUIState>((set, get) => ({
  chatId: null,
  activeRequest: null,
  queue: [],
  isSubmitting: false,
  selectedValue: '',
  inputValue: '',
  editorValue: '',

  setChatId: (chatId) => {
    set({ chatId });
    if (chatId) {
      void get().fetchPending(chatId);
    } else {
      get().reset();
    }
  },

  enqueueRequest: (req) => {
    const { activeRequest, queue } = get();
    // Avoid duplicate requests
    if (activeRequest?.request_id === req.request_id || queue.some((item) => item.request_id === req.request_id)) {
      return;
    }

    if (!activeRequest) {
      const initialSelected =
        req.request_type === 'select'
          ? (typeof req.default_value === 'string' ? req.default_value : req.options?.[0]?.value ?? '')
          : '';
      const initialInput = typeof req.default_value === 'string' ? req.default_value : '';
      const initialEditor = req.content ?? '';

      set({
        activeRequest: req,
        selectedValue: initialSelected,
        inputValue: initialInput,
        editorValue: initialEditor,
      });
    } else {
      set({ queue: [...queue, req] });
    }
  },

  setSelectedValue: (val) => set({ selectedValue: val }),
  setInputValue: (val) => set({ inputValue: val }),
  setEditorValue: (val) => set({ editorValue: val }),

  resolveCurrent: async (customValue) => {
    const { activeRequest, chatId, queue, selectedValue, inputValue, editorValue } = get();
    if (!activeRequest || !chatId) {
      return false;
    }

    set({ isSubmitting: true });
    try {
      let finalValue: string | boolean | null = null;
      if (customValue !== undefined) {
        finalValue = customValue;
      } else if (activeRequest.request_type === 'select') {
        finalValue = selectedValue;
      } else if (activeRequest.request_type === 'confirm') {
        finalValue = typeof activeRequest.default_value === 'boolean' ? activeRequest.default_value : true;
      } else if (activeRequest.request_type === 'input') {
        finalValue = inputValue;
      } else if (activeRequest.request_type === 'editor') {
        finalValue = editorValue;
      }

      await submitUIResponse(chatId, activeRequest.request_id, {
        value: finalValue,
        cancelled: false,
      });

      // Shift next request from queue
      const nextRequest = queue[0] ?? null;
      const nextQueue = queue.slice(1);

      set({
        activeRequest: nextRequest,
        queue: nextQueue,
        isSubmitting: false,
        selectedValue:
          nextRequest?.request_type === 'select'
            ? (typeof nextRequest.default_value === 'string'
                ? nextRequest.default_value
                : nextRequest.options?.[0]?.value ?? '')
            : '',
        inputValue: typeof nextRequest?.default_value === 'string' ? nextRequest.default_value : '',
        editorValue: nextRequest?.content ?? '',
      });
      return true;
    } catch (err) {
      console.error('[useExtensionUIStore] Failed to resolve UI request', err);
      set({ isSubmitting: false });
      return false;
    }
  },

  cancelCurrent: async (reason = 'Operator dismissed dialog') => {
    const { activeRequest, chatId, queue } = get();
    if (!activeRequest || !chatId) {
      return false;
    }

    set({ isSubmitting: true });
    try {
      await cancelUIRequest(chatId, activeRequest.request_id, reason);

      const nextRequest = queue[0] ?? null;
      const nextQueue = queue.slice(1);

      set({
        activeRequest: nextRequest,
        queue: nextQueue,
        isSubmitting: false,
        selectedValue:
          nextRequest?.request_type === 'select'
            ? (typeof nextRequest.default_value === 'string'
                ? nextRequest.default_value
                : nextRequest.options?.[0]?.value ?? '')
            : '',
        inputValue: typeof nextRequest?.default_value === 'string' ? nextRequest.default_value : '',
        editorValue: nextRequest?.content ?? '',
      });
      return true;
    } catch (err) {
      console.error('[useExtensionUIStore] Failed to cancel UI request', err);
      set({ isSubmitting: false });
      return false;
    }
  },

  fetchPending: async (chatId) => {
    const requests = await fetchPendingUIRequests(chatId);
    if (!requests || requests.length === 0) {
      return;
    }

    const { activeRequest, queue } = get();
    const existingIds = new Set<string>();
    if (activeRequest) {
      existingIds.add(activeRequest.request_id);
    }
    for (const item of queue) {
      existingIds.add(item.request_id);
    }

    for (const req of requests) {
      if (!existingIds.has(req.request_id)) {
        get().enqueueRequest(req);
        existingIds.add(req.request_id);
      }
    }
  },

  reset: () => {
    set({
      chatId: null,
      activeRequest: null,
      queue: [],
      isSubmitting: false,
      selectedValue: '',
      inputValue: '',
      editorValue: '',
    });
  },
}));
