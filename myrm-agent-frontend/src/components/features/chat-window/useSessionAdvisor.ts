/**
 * [INPUT]
 * - window event `copilot-open-advisor` (POS: 消息选中工具栏与命令入口请求打开顾问，detail 带问题与选中文本)
 *
 * [OUTPUT]
 * - useSessionAdvisor: 会话顾问面板的受控状态（open / question / selection）与关闭回调
 *
 * [POS]
 * ChatWindow 的顾问层。面板关闭时清空问题与选中文本，下次打开不会带着上一次的上下文。
 */

import { useCallback, useEffect, useState } from 'react';

export interface SessionAdvisorState {
  open: boolean;
  question: string;
  selection: string | undefined;
  onOpenChange: (open: boolean) => void;
}

export function useSessionAdvisor(): SessionAdvisorState {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [selection, setSelection] = useState<string | undefined>();

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ question?: string; selection?: string }>).detail;
      setQuestion(detail?.question ?? '');
      setSelection(detail?.selection);
      setOpen(true);
    };
    window.addEventListener('copilot-open-advisor', handler);
    return () => window.removeEventListener('copilot-open-advisor', handler);
  }, []);

  const onOpenChange = useCallback((nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setQuestion('');
      setSelection(undefined);
    }
  }, []);

  return { open, question, selection, onOpenChange };
}
