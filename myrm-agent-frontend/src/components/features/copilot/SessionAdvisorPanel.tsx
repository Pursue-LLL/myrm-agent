'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import {
  askAdvisor,
  clearAdvisorMessages,
  fetchAdvisorMessages,
  type AdvisorMessage,
} from '@/services/copilot';
import { Button } from '@/components/primitives/button';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/primitives/sheet';

interface SessionAdvisorPanelProps {
  chatId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialQuestion?: string;
  selectionSnippet?: string;
}

export default function SessionAdvisorPanel({
  chatId,
  open,
  onOpenChange,
  initialQuestion = '',
  selectionSnippet,
}: SessionAdvisorPanelProps) {
  const t = useTranslations('copilot');
  const [messages, setMessages] = useState<AdvisorMessage[]>([]);
  const [input, setInput] = useState(initialQuestion);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const autoAskKeyRef = useRef('');

  const loadMessages = useCallback(async () => {
    const rows = await fetchAdvisorMessages(chatId);
    setMessages(rows);
  }, [chatId]);

  const performAsk = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || pendingRef.current) {return false;}
      pendingRef.current = true;
      setPending(true);
      setInput('');
      try {
        const result = await askAdvisor(chatId, trimmed, selectionSnippet);
        if (result) {
          await loadMessages();
        }
        return Boolean(result);
      } finally {
        pendingRef.current = false;
        setPending(false);
      }
    },
    [chatId, loadMessages, selectionSnippet],
  );

  useEffect(() => {
    if (!open) {
      autoAskKeyRef.current = '';
      return;
    }
    void loadMessages();
  }, [open, loadMessages]);

  useEffect(() => {
    if (!open) {return;}
    const question = initialQuestion.trim();
    if (!question) {return;}
    const dedupeKey = `${chatId}:${question}:${selectionSnippet ?? ''}`;
    if (autoAskKeyRef.current === dedupeKey) {return;}
    autoAskKeyRef.current = dedupeKey;
    void performAsk(question);
  }, [open, initialQuestion, chatId, selectionSnippet, performAsk]);

  const submit = useCallback(async () => {
    await performAsk(input);
  }, [input, performAsk]);

  const handleClear = useCallback(async () => {
    await clearAdvisorMessages(chatId);
    setMessages([]);
    autoAskKeyRef.current = '';
  }, [chatId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        data-testid="copilot-advisor-panel"
        className="flex w-full flex-col sm:max-w-md"
      >
        <SheetHeader className="flex flex-row items-center justify-between space-y-0">
          <SheetTitle>{t('advisorTitle')}</SheetTitle>
          <Button type="button" variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </SheetHeader>
        <p className="text-xs text-muted-foreground">{t('advisorHint')}</p>
        <div data-testid="copilot-advisor-messages" className="min-h-0 flex-1 overflow-y-auto space-y-3 py-3">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('advisorEmpty')}</p>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-primary/10 text-foreground'
                  : 'bg-muted text-foreground/90'
              }`}
            >
              {msg.role === 'assistant' ? (
                <div className="mb-1 text-[10px] font-medium text-muted-foreground">
                  {msg.tier === 'tier0' ? t('tierRules') : t('tierLite')}
                </div>
              ) : null}
              {msg.content}
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-2 border-t pt-3">
          <textarea
            data-testid="copilot-advisor-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={3}
            placeholder={t('advisorPlaceholder')}
            className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <div className="flex gap-2">
            <Button
              type="button"
              data-testid="copilot-advisor-send"
              className="flex-1"
              disabled={pending}
              onClick={() => void submit()}
            >
              {pending ? t('advisorSending') : t('advisorSend')}
            </Button>
            <Button type="button" variant="outline" onClick={() => void handleClear()}>
              {t('advisorClear')}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
