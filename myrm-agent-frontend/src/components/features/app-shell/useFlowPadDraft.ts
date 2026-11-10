/**
 * [INPUT]
 * - FlowPadMode (POS: 面板模式)
 *
 * [OUTPUT]
 * - useFlowPadDraft: 输入草稿与截图放大图，随面板会话重置。
 *
 * [POS]
 * FlowPad 的会话内输入状态。每次打开、换截图或换模式都回到起始文本并收起放大图；
 * 关闭时保持原样，淡出动画期间内容不会闪成空白。
 */
import { useState } from 'react';
import type { FlowPadMode } from '@/store/useFlowPadStore';

interface FlowPadDraftSession {
  isOpen: boolean;
  mode: FlowPadMode;
  sourcePid: number | null;
  /** Text the draft starts from in this session. */
  initialText: string;
}

export function useFlowPadDraft({ isOpen, mode, sourcePid, initialText }: FlowPadDraftSession) {
  const [text, setText] = useState(initialText);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [seenSession, setSeenSession] = useState({ isOpen, mode, sourcePid, initialText });

  // A new session is applied while rendering, so it never paints the previous session's draft first.
  if (
    seenSession.isOpen !== isOpen ||
    seenSession.mode !== mode ||
    seenSession.sourcePid !== sourcePid ||
    seenSession.initialText !== initialText
  ) {
    setSeenSession({ isOpen, mode, sourcePid, initialText });
    if (isOpen) {
      setText(initialText);
      setLightboxSrc(null);
    }
  }

  return { text, setText, lightboxSrc, setLightboxSrc };
}
