/**
 * [INPUT]
 * - zustand (POS: 状态管理)
 *
 * [OUTPUT]
 * - useFlowPadStore: FlowPad 模态窗口状态管理
 * - FlowPadCapture: 截屏数据结构
 *
 * [POS] FlowPad 全局状态。管理模态窗口开关、截屏上下文列表、初始文本。
 * 服务 Appshot 截屏和 deep link Quick Ask 两种入口场景。
 */

import { create } from 'zustand';

const MAX_CAPTURES = 10;

export interface FlowPadCapture {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  timestamp: number;
}

interface FlowPadState {
  isOpen: boolean;
  captures: FlowPadCapture[];
  initialText: string;

  /** 打开 FlowPad（无截屏上下文，用于 deep link / Quick Ask） */
  open: (text?: string) => void;
  /** 添加截屏并打开 FlowPad，已打开则追加截图 */
  addCapture: (capture: FlowPadCapture) => void;
  /** 移除指定索引的截屏 */
  removeCapture: (index: number) => void;
  /** 关闭 FlowPad 并释放截屏内存 */
  close: () => void;
}

export const useFlowPadStore = create<FlowPadState>((set) => ({
  isOpen: false,
  captures: [],
  initialText: '',

  open: (text = '') => set({ isOpen: true, initialText: text }),

  addCapture: (capture) =>
    set((state) => {
      if (state.captures.length >= MAX_CAPTURES) return state;
      return { isOpen: true, captures: [...state.captures, capture] };
    }),

  removeCapture: (index) =>
    set((state) => ({
      captures: state.captures.filter((_, i) => i !== index),
    })),

  close: () => set({ isOpen: false, captures: [], initialText: '' }),
}));
