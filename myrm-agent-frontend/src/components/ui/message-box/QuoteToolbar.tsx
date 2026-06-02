'use client';

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Quote, Copy } from 'lucide-react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import useQuoteStore from '@/store/useQuoteStore';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';

interface SelectionRect {
  x: number;
  y: number;
}

interface QuoteToolbarState {
  visible: boolean;
  text: string;
  isCode: boolean;
  rect: SelectionRect;
  flipDown: boolean;
  sourceMessageId: string;
}

const TOOLBAR_HEIGHT = 36;
const TOOLBAR_GAP = 6;
const QUOTE_TEXT_MAX_LEN = 2000;

function isInsideCodeBlock(node: Node): boolean {
  let el: Element | null = node instanceof Element ? node : node.parentElement;
  while (el) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'pre' || (tag === 'code' && el.parentElement?.tagName.toLowerCase() === 'pre')) {
      return true;
    }
    el = el.parentElement;
  }
  return false;
}

function formatQuoteText(text: string, isCode: boolean): string {
  if (isCode) {
    return `\`\`\`\n${text}\n\`\`\`\n\n`;
  }
  const lines = text.split('\n');
  return lines.map((line) => `> ${line}`).join('\n') + '\n\n';
}

export function useQuoteSelection(containerRef: React.RefObject<HTMLDivElement | null>) {
  const [state, setState] = useState<QuoteToolbarState>({
    visible: false,
    text: '',
    isCode: false,
    rect: { x: 0, y: 0 },
    flipDown: false,
    sourceMessageId: '',
  });

  const dismiss = useCallback(() => {
    setState((prev) => (prev.visible ? { ...prev, visible: false } : prev));
  }, []);

  const handleSelectionEnd = useCallback(() => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      dismiss();
      return;
    }

    const selectedText = selection.toString().trim();
    if (!selectedText || selectedText.length < 2) {
      dismiss();
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    const anchorNode = selection.anchorNode;
    if (!anchorNode || !container.contains(anchorNode)) {
      dismiss();
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    const toolbarWidth = 120;
    const x = Math.max(
      8,
      Math.min(rect.left + rect.width / 2 - toolbarWidth / 2, window.innerWidth - toolbarWidth - 8),
    );

    const topY = rect.top - TOOLBAR_HEIGHT - TOOLBAR_GAP;
    const flipDown = topY < 8;
    const y = flipDown ? rect.bottom + TOOLBAR_GAP : topY;

    const isCode = isInsideCodeBlock(anchorNode);
    const sourceMessageId = container.dataset.messageId ?? '';

    setState({
      visible: true,
      text: selectedText.slice(0, QUOTE_TEXT_MAX_LEN),
      isCode,
      rect: { x, y },
      flipDown,
      sourceMessageId,
    });
  }, [containerRef, dismiss]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const onMouseUp = () => {
      requestAnimationFrame(handleSelectionEnd);
    };

    container.addEventListener('mouseup', onMouseUp);
    container.addEventListener('touchend', onMouseUp);

    const onClickOutside = (e: MouseEvent) => {
      if (!state.visible) return;
      const target = e.target as Node;
      const toolbar = document.getElementById('quote-toolbar-portal');
      if (toolbar?.contains(target)) return;
      if (container.contains(target)) return;
      dismiss();
    };

    document.addEventListener('mousedown', onClickOutside);

    return () => {
      container.removeEventListener('mouseup', onMouseUp);
      container.removeEventListener('touchend', onMouseUp);
      document.removeEventListener('mousedown', onClickOutside);
    };
  }, [containerRef, handleSelectionEnd, dismiss, state.visible]);

  return { state, dismiss };
}

export function QuoteToolbar({ state, onDismiss }: { state: QuoteToolbarState; onDismiss: () => void }) {
  const t = useTranslations('chat');
  const [copied, setCopied] = useState(false);

  const handleQuote = useCallback(() => {
    const formatted = formatQuoteText(state.text, state.isCode);
    const { inputMessage, setInputMessage } = useChatStore.getState();
    const newValue = inputMessage ? `${inputMessage}\n${formatted}` : formatted;
    setInputMessage(newValue);

    if (state.sourceMessageId) {
      useQuoteStore.getState().setQuote({
        sourceMessageId: state.sourceMessageId,
        quotedText: state.text,
      });
    }

    window.getSelection()?.removeAllRanges();
    onDismiss();

    requestAnimationFrame(() => {
      const textarea = document.querySelector<HTMLTextAreaElement>('textarea[data-chat-input]');
      if (textarea) {
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      }
    });
  }, [state.text, state.isCode, state.sourceMessageId, onDismiss]);

  const handleCopy = useCallback(async () => {
    await writeToClipboard(state.text);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
      onDismiss();
      window.getSelection()?.removeAllRanges();
    }, 800);
  }, [state.text, onDismiss]);

  if (typeof window === 'undefined') return null;

  return createPortal(
    <AnimatePresence>
      {state.visible && (
        <motion.div
          id="quote-toolbar-portal"
          initial={{ opacity: 0, scale: 0.92, y: state.flipDown ? -4 : 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: state.flipDown ? -4 : 4 }}
          transition={{ duration: 0.12, ease: 'easeOut' }}
          style={{
            position: 'fixed',
            left: state.rect.x,
            top: state.rect.y,
            zIndex: 50000,
          }}
          className="flex items-center gap-0.5 rounded-lg border bg-popover px-1 py-0.5 shadow-lg"
        >
          <button
            onClick={handleQuote}
            className="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium text-popover-foreground hover:bg-accent transition-colors"
            title={t('quoteSelection')}
          >
            <Quote className="h-3.5 w-3.5 text-primary" />
            <span>{t('quoteSelection')}</span>
          </button>
          <div className="h-4 w-px bg-border" />
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium text-popover-foreground hover:bg-accent transition-colors"
            title={t('copySelection')}
          >
            <Copy className="h-3.5 w-3.5" />
            <span>{copied ? '✓' : t('copySelection')}</span>
          </button>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
