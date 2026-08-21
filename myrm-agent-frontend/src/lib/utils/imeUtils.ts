/**
 * IME (Input Method Editor) 输入法兼容性守卫工具函数
 *
 * 解决 Windows、macOS 以及各类移动端 WebView 在中文/日文/韩文输入法候选词确认（Enter / Space）时，
 * 因浏览器事件时序竞争导致的 isComposing 提前翻转或 keyCode=229 / key='Process' 导致的误触提交问题。
 */

import type React from 'react';

export type KeyboardEventLike =
  | React.KeyboardEvent
  | KeyboardEvent
  | {
      isComposing?: boolean;
      key?: string;
      keyCode?: number;
      which?: number;
      nativeEvent?: {
        isComposing?: boolean;
        keyCode?: number;
      };
    };

/**
 * 严格判定当前键盘事件是否处于 IME 输入法组合键阶段（候选词挑选 / 拼音输入中）
 *
 * @param event React 键盘事件或原生 KeyboardEvent
 * @returns true 表示正在输入法组合中，业务层应 return 阻止提交或快捷指令触发
 */
export function isImeComposing(event: KeyboardEventLike): boolean {
  if (!event) {
    return false;
  }

  // 1. 标准 nativeEvent.isComposing 或 event.isComposing
  if (event.nativeEvent?.isComposing || event.isComposing) {
    return true;
  }

  // 2. W3C UI Events 标准：IME 处理中的按键 key 为 'Process'
  if (event.key === 'Process') {
    return true;
  }

  // 3. Windows IME 标准兼容：keyCode 229 为组合输入事件专属代码
  const keyCode = event.keyCode ?? event.which ?? event.nativeEvent?.keyCode;
  if (keyCode === 229) {
    return true;
  }

  return false;
}
