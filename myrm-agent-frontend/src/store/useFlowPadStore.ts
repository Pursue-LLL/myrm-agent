/**
 * [INPUT]
 * - zustand (POS: 状态管理)
 *
 * [OUTPUT]
 * - useFlowPadStore: FlowPad 模态窗口状态管理
 * - FlowPadCapture: 截屏数据结构
 *
 * [POS] FlowPad 全局状态。管理模态窗口开关、截屏上下文列表、初始文本。
 * 服务 Appshot 截屏、deep link Quick Ask 和 Inline Input 三种入口场景。
 */

import { create } from 'zustand';

const MAX_CAPTURES = 10;

export type FlowPadMode = 'chat' | 'inline';

export interface FlowPadCapture {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  timestamp: number;
}

interface FlowPadState {
  isOpen: boolean;
  mode: FlowPadMode;
  captures: FlowPadCapture[];
  initialText: string;
  /** Inline 模式下 AI 生成的结果文本（流式追加） */
  inlineResult: string;
  /** Inline 模式下是否正在生成 */
  inlineGenerating: boolean;
  /** 触发 Inline Input 时的原应用 PID */
  sourcePid: number | null;

  /** 打开 FlowPad（无截屏上下文，用于 deep link / Quick Ask） */
  open: (text?: string) => void;
  /** 以 Inline 模式打开 FlowPad */
  openInline: (capture: FlowPadCapture, sourcePid: number) => void;
  /** 添加截屏并打开 FlowPad，已打开则追加截图 */
  addCapture: (capture: FlowPadCapture) => void;
  /** 移除指定索引的截屏 */
  removeCapture: (index: number) => void;
  /** 设置 Inline 结果（流式追加） */
  appendInlineResult: (chunk: string) => void;
  /** 标记 Inline 生成完成 */
  finishInlineResult: () => void;
  /** 关闭 FlowPad 并释放截屏内存 */
  close: () => void;
}

export const useFlowPadStore = create<FlowPadState>((set) => ({
  isOpen: false,
  mode: 'chat',
  captures: [],
  initialText: '',
  inlineResult: '',
  inlineGenerating: false,
  sourcePid: null,

  open: (text = '') => set({ isOpen: true, mode: 'chat', initialText: text }),

  openInline: (capture, sourcePid) =>
    set({
      isOpen: true,
      mode: 'inline',
      captures: [capture],
      initialText: '',
      inlineResult: '',
      inlineGenerating: false,
      sourcePid,
    }),

  addCapture: (capture) =>
    set((state) => {
      if (state.captures.length >= MAX_CAPTURES) return state;
      return { isOpen: true, captures: [...state.captures, capture] };
    }),

  removeCapture: (index) =>
    set((state) => ({
      captures: state.captures.filter((_, i) => i !== index),
    })),

  appendInlineResult: (chunk) =>
    set((state) => ({
      inlineResult: state.inlineResult + chunk,
      inlineGenerating: true,
    })),

  finishInlineResult: () => set({ inlineGenerating: false }),

  close: () =>
    set({
      isOpen: false,
      mode: 'chat',
      captures: [],
      initialText: '',
      inlineResult: '',
      inlineGenerating: false,
      sourcePid: null,
    }),
}));
