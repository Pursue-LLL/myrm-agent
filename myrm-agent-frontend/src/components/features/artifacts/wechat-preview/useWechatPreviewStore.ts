/**
 * [INPUT]
 * - wechatPreviewTypes: DeviceViewportMode, WechatThemeId, FontSizeScale
 *
 * [OUTPUT]
 * - useWechatPreviewStore: Zustand store managing WeChat article formatting preferences and viewport states
 *
 * [POS]
 * State management for WeChat Social Article Formatter & Multi-Device Previewer (Item 45 P0).
 * Strictly under 120 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  DeviceViewportMode,
  FontSizeScale,
  WechatThemeId,
} from './wechatPreviewTypes';

interface WechatPreviewState {
  viewport: DeviceViewportMode;
  themeId: WechatThemeId;
  scale: FontSizeScale;
  copied: boolean;

  setViewport: (viewport: DeviceViewportMode) => void;
  setThemeId: (themeId: WechatThemeId) => void;
  setScale: (scale: FontSizeScale) => void;
  setCopied: (copied: boolean) => void;
  triggerCopiedFeedback: () => void;
  reset: () => void;
}

let copiedTimer: ReturnType<typeof setTimeout> | null = null;

export const useWechatPreviewStore = create<WechatPreviewState>((set) => ({
  viewport: 'mobile',
  themeId: 'classic',
  scale: 'normal',
  copied: false,

  setViewport: (viewport: DeviceViewportMode) => {
    set({ viewport });
  },

  setThemeId: (themeId: WechatThemeId) => {
    set({ themeId });
  },

  setScale: (scale: FontSizeScale) => {
    set({ scale });
  },

  setCopied: (copied: boolean) => {
    set({ copied });
  },

  triggerCopiedFeedback: () => {
    if (copiedTimer) {
      clearTimeout(copiedTimer);
    }
    set({ copied: true });
    copiedTimer = setTimeout(() => {
      set({ copied: false });
      copiedTimer = null;
    }, 2000);
  },

  reset: () => {
    if (copiedTimer) {
      clearTimeout(copiedTimer);
      copiedTimer = null;
    }
    set({
      viewport: 'mobile',
      themeId: 'classic',
      scale: 'normal',
      copied: false,
    });
  },
}));
