/**
 * [OUTPUT]
 * - useCaretPosition: 输入框光标位置（state）及其同步方法。
 *
 * [POS]
 * 斜杠命令面板与 @ 引用面板只看光标前的文本，所以光标位置要成为 state 才能驱动它们重新计算。
 * 文本变化时自动同步一次；方向键、点击等只移动光标、不改文本的操作，由调用方触发 `syncCaret`。
 */
import { type RefObject, useCallback, useEffect, useState } from 'react';

export function useCaretPosition(inputRef: RefObject<HTMLTextAreaElement | null>, text: string) {
  const [caret, setCaret] = useState(0);

  const syncCaret = useCallback(() => {
    setCaret(inputRef.current?.selectionStart || 0);
  }, [inputRef]);

  useEffect(() => {
    syncCaret();
  }, [text, syncCaret]);

  return { caret, syncCaret };
}
