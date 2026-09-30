'use client';

import React from 'react';
import { ClockCounterClockwise, X } from '@phosphor-icons/react';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { Message } from '@/store/chat/types';

interface CompactedArchiveModalProps {
  isOpen: boolean;
  isLoading: boolean;
  messages: Message[];
  title: string;
  emptyLabel: string;
  roleUserLabel: string;
  roleAssistantLabel: string;
  onClose: () => void;
  markdownLinkComponents?: Record<string, React.ComponentType<{ href?: string; children?: React.ReactNode }>>;
}

export function CompactedArchiveModal({
  isOpen,
  isLoading,
  messages,
  title,
  emptyLabel,
  roleUserLabel,
  roleAssistantLabel,
  onClose,
  markdownLinkComponents,
}: CompactedArchiveModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 md:p-8">
      <div className="bg-background border shadow-xl rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between bg-muted/30">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ClockCounterClockwise size={20} weight="duotone" />
            {title}
          </h2>
          <button type="button" onClick={onClose} className="p-2 hover:bg-muted rounded-full">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {isLoading ? (
            <div className="flex justify-center p-8">
              <div className="w-8 h-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            </div>
          ) : messages.length === 0 ? (
            <div className="text-center text-muted-foreground p-8">{emptyLabel}</div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={msg.messageId || idx}
                className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                <div className="text-xs text-muted-foreground mb-1">
                  {msg.role === 'user' ? roleUserLabel : roleAssistantLabel} •{' '}
                  {msg.createdAt ? format(new Date(msg.createdAt), 'yyyy-MM-dd HH:mm:ss') : ''}
                </div>
                <div
                  className={`prose dark:prose-invert prose-sm break-words w-full max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                    msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
                  }`}
                >
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm, remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                    components={markdownLinkComponents}
                  >
                    {msg.content || ''}
                  </ReactMarkdown>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
