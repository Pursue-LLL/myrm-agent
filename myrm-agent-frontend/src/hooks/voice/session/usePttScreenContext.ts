'use client';

/**
 * [INPUT]
 * hooks/voice/useVoicePttListener::PttScreenContext (POS: Bridges Tauri PTT events to DOM, provides PttScreenContext type)
 * hooks/voice/useSpeechInput::SpeechMode (POS: Speech-to-text input with multi-backend STT)
 *
 * [OUTPUT]
 * usePttScreenContext: Returns a function that fuses the latest PTT screen context into an outgoing voice message
 * PttMessagePayload: Message text plus the screenshots that ride with it
 *
 * [POS]
 * PTT screen context fusion (Tauri desktop). The Rust side emits `voice-ptt-context` asynchronously after the key press
 * (screenshot + window text); this hook stores it and, when the transcript arrives, attaches it to the message.
 */

import { useCallback, useEffect, useRef } from 'react';
import type { SpeechMode } from '../useSpeechInput';
import type { PttScreenContext } from '../useVoicePttListener';

export interface PttMessagePayload {
  text: string;
  visionFrames?: string[];
}

export function usePttScreenContext(speechMode: SpeechMode): (text: string) => Promise<PttMessagePayload> {
  // PTT 屏幕上下文：Rust 端在 PTT 按下时异步截图后发射 voice-ptt-context DOM 事件
  const pttScreenContextRef = useRef<PttScreenContext | null>(null);
  const pttPendingPromiseRef = useRef<{ resolve: (ctx: PttScreenContext | null) => void } | null>(null);

  useEffect(() => {
    const handlePttStart = () => {
      pttScreenContextRef.current = null;
    };

    const handlePttContext = (e: Event) => {
      const detail = (e as CustomEvent<PttScreenContext>).detail;
      if (detail?.screenshot || detail?.extractedText || detail?.selectedText) {
        pttScreenContextRef.current = detail;
        if (pttPendingPromiseRef.current) {
          pttPendingPromiseRef.current.resolve(detail);
          pttPendingPromiseRef.current = null;
        }
      }
    };

    window.addEventListener('voice-ptt-start', handlePttStart);
    window.addEventListener('voice-ptt-context', handlePttContext);
    return () => {
      window.removeEventListener('voice-ptt-start', handlePttStart);
      window.removeEventListener('voice-ptt-context', handlePttContext);
    };
  }, []);

  return useCallback(
    async (text: string): Promise<PttMessagePayload> => {
      let visionFrames: string[] | undefined;
      let finalText = text;

      // PTT 屏幕上下文汇聚屏障锁（Barrier Sync）：
      // 若当前处于 PTT 模式且截图仍在传输，等待最多 250ms 汇聚窗口
      let pttCtx = pttScreenContextRef.current;
      if (!pttCtx && speechMode === 'push-to-talk') {
        pttCtx = await new Promise<PttScreenContext | null>((resolve) => {
          const timer = setTimeout(() => {
            pttPendingPromiseRef.current = null;
            resolve(null);
          }, 250);
          pttPendingPromiseRef.current = {
            resolve: (ctx) => {
              clearTimeout(timer);
              resolve(ctx);
            },
          };
        });
      }
      pttScreenContextRef.current = null;

      if (pttCtx && Date.now() - pttCtx.timestamp < 30_000) {
        if (pttCtx.screenshot) {
          visionFrames = [pttCtx.screenshot];
        }

        const contextParts: string[] = [];
        if (pttCtx.windowTitle) {
          contextParts.push(`[Active Window: ${pttCtx.windowTitle}]`);
        }
        if (pttCtx.selectedText && pttCtx.selectedText.trim()) {
          contextParts.push(`[Selected Text: ${pttCtx.selectedText.trim().slice(0, 3000)}]`);
        } else if (pttCtx.extractedText && pttCtx.extractedText.trim()) {
          contextParts.push(`[Screen Text: ${pttCtx.extractedText.trim().slice(0, 2000)}]`);
        }
        if (contextParts.length > 0) {
          finalText = `${contextParts.join('\n')}\n\n${text}`;
        }
      }

      return { text: finalText, visionFrames };
    },
    [speechMode],
  );
}
