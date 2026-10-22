'use client';

/**
 * [INPUT]
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: Bot, ChevronDown, ChevronUp, Send, Sparkles, X, MessageSquare)
 *
 * [OUTPUT]
 * ManagerConversationTray: Floating drawer tray for prompt interactions with the Workspace Manager Agent.
 *
 * [POS]
 * Manager conversation companion tray for Personal Workspace Cockpit. Aligns with LoopX dashboard companion tray.
 */

import React, { useState, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Bot, ChevronDown, ChevronUp, Send, Sparkles, X, MessageSquare } from 'lucide-react';

interface ManagerConversationTrayProps {
  onSendMessage?: (text: string) => void;
  className?: string;
}

const QUICK_COMMANDS = [
  'Summarize in-progress goals',
  'What is blocking my approval?',
  'Check system probe health',
];

export const ManagerConversationTray: React.FC<ManagerConversationTrayProps> = ({
  onSendMessage,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [inputText, setInputText] = useState('');
  const [messages, setMessages] = useState<Array<{ id: string; sender: 'user' | 'agent'; text: string }>>([
    {
      id: 'init-msg',
      sender: 'agent',
      text: 'Hello! I am your Workspace Manager Agent. I monitor your 4 task swimlanes and offline progress. How can I assist you?',
    },
  ]);

  const handleSend = useCallback(() => {
    const trimmed = inputText.trim();
    if (!trimmed) {
      return;
    }

    const userMsgId = `user-${Date.now()}`;
    setMessages((prev) => [...prev, { id: userMsgId, sender: 'user', text: trimmed }]);
    setInputText('');

    if (onSendMessage) {
      onSendMessage(trimmed);
    }

    // Mock instant response for manager guidance
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `agent-${Date.now()}`,
          sender: 'agent',
          text: `Acknowledged: "${trimmed}". The workspace monitors and swimlanes have refreshed.`,
        },
      ]);
    }, 400);
  }, [inputText, onSendMessage]);

  const handleCommandClick = useCallback(
    (cmd: string) => {
      setInputText(cmd);
      if (!isOpen) {
        setIsOpen(true);
      }
    },
    [isOpen],
  );

  return (
    <div
      data-testid="manager-conversation-tray"
      className={cn('fixed bottom-4 right-4 z-40 flex flex-col items-end', className)}
    >
      {/* Expanded Chat Drawer */}
      {isOpen && (
        <section
          aria-label="Workspace Manager Companion"
          data-testid="manager-tray-expanded"
          className="w-80 sm:w-96 rounded-xl border border-border/80 bg-background/95 backdrop-blur-md shadow-2xl flex flex-col mb-2 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-150"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 bg-primary/10 border-b border-border text-xs">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div>
                <span className="font-semibold text-foreground">Workspace Manager</span>
                <span className="block text-[10px] text-muted-foreground">Always-on companion</span>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                aria-label="Minimize companion tray"
                title="Minimize"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                aria-label="Close companion tray"
                title="Close"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Quick Command Chips */}
          <div className="px-3 py-2 bg-muted/30 border-b border-border/50 flex flex-wrap gap-1">
            {QUICK_COMMANDS.map((cmd) => (
              <button
                key={cmd}
                type="button"
                onClick={() => handleCommandClick(cmd)}
                className="px-2 py-0.5 rounded-full bg-background border border-border/70 text-[10px] text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors flex items-center gap-1"
              >
                <Sparkles className="w-2.5 h-2.5 text-primary" />
                <span>{cmd}</span>
              </button>
            ))}
          </div>

          {/* Message History Stream */}
          <div className="h-56 overflow-y-auto p-3 space-y-2 text-xs">
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  'flex flex-col max-w-[85%] rounded-lg p-2.5 text-xs',
                  m.sender === 'user'
                    ? 'ml-auto bg-primary text-primary-foreground'
                    : 'mr-auto bg-muted/60 text-foreground border border-border/40',
                )}
              >
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>
            ))}
          </div>

          {/* Prompt Input Box */}
          <div className="p-2.5 bg-background border-t border-border flex items-center gap-1.5">
            <input
              type="text"
              data-testid="manager-tray-input"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleSend();
                }
              }}
              placeholder="Ask manager about workspace..."
              className="flex-1 px-2.5 py-1.5 rounded-md border border-input bg-background text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              type="button"
              data-testid="manager-tray-send-btn"
              onClick={handleSend}
              disabled={!inputText.trim()}
              className="p-1.5 rounded-md bg-primary text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors"
              aria-label="Send message to manager"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </section>
      )}

      {/* Floating Pill Trigger */}
      <button
        type="button"
        data-testid="manager-tray-toggle"
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          'flex items-center gap-2 px-3.5 py-2 rounded-full shadow-lg border transition-all duration-150',
          isOpen
            ? 'bg-muted text-muted-foreground border-border hover:bg-muted/80'
            : 'bg-primary text-primary-foreground border-primary/20 hover:scale-105 active:scale-95',
        )}
        aria-expanded={isOpen}
        aria-label="Toggle workspace manager tray"
      >
        <Bot className="w-4 h-4" />
        <span className="text-xs font-semibold">Manager Tray</span>
        {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
      </button>
    </div>
  );
};

export default React.memo(ManagerConversationTray);
