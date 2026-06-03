'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuickAskStore } from '@/store/useQuickAskStore';
import { Dialog, DialogContent } from '@/components/primitives/dialog';
import { Textarea } from '@/components/primitives/textarea';
import { Button } from '@/components/primitives/button';
import { Send, X } from 'lucide-react';
import { useRouter } from 'next/navigation';

/**
 * [POS] Global Quick Ask Modal.
 * Triggered by the /ask deep link. Provides a Spotlight-like quick interaction.
 */
export function QuickAskModal() {
  const { isOpen, initialText, closeQuickAsk } = useQuickAskStore();
  const [text, setText] = useState(initialText);
  const router = useRouter();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen) {
      setText(initialText);
      // Auto focus after a short delay to ensure modal is rendered
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
  }, [isOpen, initialText]);

  const handleSubmit = () => {
    if (!text.trim()) return;

    // In a real implementation, this would either:
    // 1. Send the message to a temporary "Quick Ask" agent session right here.
    // 2. Or redirect to a new chat with the pre-filled text.
    // For now, we redirect to a new chat to leverage existing chat UI.

    closeQuickAsk();
    // Encode text and redirect to home/chat creation
    router.push(`/?q=${encodeURIComponent(text)}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // [Fix 1.3] 跳过 IME 组合输入阶段的按键拦截
    if (e.nativeEvent.isComposing) {
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && closeQuickAsk()}>
      <DialogContent className="sm:max-w-[600px] p-0 overflow-hidden bg-background/80 backdrop-blur-xl border-muted shadow-2xl">
        <div className="flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b border-border/50 bg-muted/30">
            <span className="text-xs font-medium text-muted-foreground">Quick Ask</span>
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={closeQuickAsk}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="p-4 relative">
            <Textarea
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask MyrmAgent anything..."
              className="min-h-[100px] resize-none border-0 focus-visible:ring-0 text-lg p-0 bg-transparent"
            />
            <div className="absolute bottom-4 right-4">
              <Button size="icon" className="h-8 w-8 rounded-full" onClick={handleSubmit} disabled={!text.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
