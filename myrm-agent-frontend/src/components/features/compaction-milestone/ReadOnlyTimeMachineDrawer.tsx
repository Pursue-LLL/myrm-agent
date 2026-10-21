'use client';

/**
 * [INPUT]
 * - CompactedMessageSnapshot from ./compactionTypes
 * - useTranslations from next-intl (namespace: 'compaction.timeMachine')
 *
 * [OUTPUT]
 * - ReadOnlyTimeMachineDrawer: In-place expandable time-machine sheet showing raw archived messages
 *
 * [POS]
 * Audit viewer for compacted messages (Item 27).
 * Single file < 180 lines. Zero `any` types. Zero native emoji.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import { History, ShieldAlert, User, Bot, Wrench, ChevronUp } from 'lucide-react';
import type { CompactedMessageSnapshot } from './compactionTypes';

interface ReadOnlyTimeMachineDrawerProps {
  messages: CompactedMessageSnapshot[];
  onClose: () => void;
  className?: string;
}

export function ReadOnlyTimeMachineDrawer({
  messages,
  onClose,
  className = '',
}: ReadOnlyTimeMachineDrawerProps) {
  const t = useTranslations('compaction.timeMachine');

  const getRoleIcon = (role: CompactedMessageSnapshot['role']) => {
    switch (role) {
      case 'user':
        return <User className="w-3.5 h-3.5 text-blue-500 shrink-0" />;
      case 'assistant':
        return <Bot className="w-3.5 h-3.5 text-emerald-500 shrink-0" />;
      case 'tool':
        return <Wrench className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
      default:
        return <History className="w-3.5 h-3.5 text-muted-foreground shrink-0" />;
    }
  };

  const getRoleLabel = (role: CompactedMessageSnapshot['role']) => {
    switch (role) {
      case 'user':
        return t('originalRoleUser');
      case 'assistant':
        return t('originalRoleAssistant');
      case 'tool':
        return t('originalRoleTool');
      default:
        return role;
    }
  };

  return (
    <section
      aria-label="Read-Only Transcript Time Machine"
      className={`mt-2 rounded-2xl border border-dashed border-border/80 bg-muted/40 p-3 flex flex-col gap-2.5 backdrop-blur-xs select-text ${className}`}
    >
      {/* Time Machine Header Bar */}
      <div className="flex items-center justify-between gap-2 border-b border-border/50 pb-2 text-xs">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-primary" />
          <span className="font-semibold text-foreground">
            {t('openButton', { count: messages.length })}
          </span>
          <span className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium">
            <ShieldAlert className="w-3 h-3" />
            <span>{t('watermarkBadge')}</span>
          </span>
        </div>

        <button
          type="button"
          onClick={onClose}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground p-1 rounded-md transition-colors"
        >
          <ChevronUp className="w-3.5 h-3.5" />
          <span>{t('closeButton')}</span>
        </button>
      </div>

      {/* Messages List Container */}
      <div className="max-h-72 overflow-y-auto flex flex-col gap-2 pr-1 font-mono text-xs">
        {messages.length === 0 ? (
          <div className="py-4 text-center text-muted-foreground text-xs italic">
            {t('emptyMessages')}
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={msg.id || `time-msg-${idx}`}
              className="p-2.5 rounded-xl bg-background/70 border border-border/40 flex flex-col gap-1 shadow-2xs opacity-90 hover:opacity-100 transition-opacity"
            >
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <div className="flex items-center gap-1.5 font-sans font-medium text-foreground">
                  {getRoleIcon(msg.role)}
                  <span>{getRoleLabel(msg.role)}</span>
                  {msg.toolName && (
                    <span className="text-[10px] px-1 rounded bg-muted text-muted-foreground font-mono">
                      {msg.toolName}
                    </span>
                  )}
                </div>
                {msg.timestamp && (
                  <span className="text-[10px] text-muted-foreground/70 font-mono">
                    {msg.timestamp}
                  </span>
                )}
              </div>
              <div className="text-[11px] leading-relaxed text-foreground/80 whitespace-pre-wrap select-text font-sans">
                {msg.content}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
