'use client';

/**
 * [INPUT]
 * - groupChatTypes: AgentMentionPopupProps, GroupChatBotMember
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - AgentMentionPopup: Inline @-mention popup list for selecting agents
 *
 * [POS]
 * Group Chat composer popup auto-completing @ mentions and routing tasks to primary agents.
 */

import React, { useState, useEffect, useMemo, useCallback, KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Target, AtSign, Search } from 'lucide-react';
import {
  AgentMentionPopupProps,
  GroupChatBotMember,
} from './groupChatTypes';

export const AgentMentionPopup: React.FC<AgentMentionPopupProps> = ({
  isOpen,
  filterText = '',
  members,
  onSelectAgent,
  onClose,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('groupChat.mention');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  const [selectedIndex, setSelectedIndex] = useState<number>(0);

  const cleanFilter = filterText.startsWith('@') ? filterText.slice(1).toLowerCase().trim() : filterText.toLowerCase().trim();

  const filteredMembers = useMemo(() => {
    if (!cleanFilter) {
      return members;
    }
    return members.filter((member) => {
      const matchName = member.name.toLowerCase().includes(cleanFilter);
      const matchRole = member.role.toLowerCase().includes(cleanFilter);
      const matchId = member.id.toLowerCase().includes(cleanFilter);
      return matchName || matchRole || matchId;
    });
  }, [members, cleanFilter]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredMembers]);

  const handleSelect = useCallback(
    (member: GroupChatBotMember) => {
      onSelectAgent(member);
      onClose();
    },
    [onSelectAgent, onClose],
  );

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const onWindowKeyDown = (e: globalThis.KeyboardEvent) => {
      if (filteredMembers.length === 0) {
        return;
      }

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredMembers.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredMembers.length) % filteredMembers.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const target = filteredMembers[selectedIndex];
        if (target) {
          handleSelect(target);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', onWindowKeyDown);
    return () => {
      window.removeEventListener('keydown', onWindowKeyDown);
    };
  }, [isOpen, filteredMembers, selectedIndex, handleSelect, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      aria-label={t('mentionTitle')}
      data-testid="agent-mention-popup"
      className={`absolute bottom-full left-0 mb-2 w-72 rounded-2xl border border-border/80 bg-popover/95 p-1.5 shadow-xl backdrop-blur-md z-50 animate-in fade-in zoom-in-95 duration-150 ${className}`}
    >
      <div className="flex items-center gap-1.5 px-2 py-1 border-b border-border/50 text-[11px] font-semibold text-muted-foreground">
        <AtSign className="h-3.5 w-3.5 text-primary" />
        <span>{t('mentionTitle')}</span>
        {cleanFilter ? (
          <span className="ml-auto flex items-center gap-0.5 text-[10px] text-muted-foreground/70 font-mono">
            <Search className="h-2.5 w-2.5" />
            <span>{cleanFilter}</span>
          </span>
        ) : null}
      </div>

      <div className="max-h-60 overflow-y-auto py-1 space-y-0.5">
        {filteredMembers.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">
            {t('noMatch')}
          </div>
        ) : (
          filteredMembers.map((member, index) => {
            const isSelected = index === selectedIndex;

            return (
              <button
                key={member.id}
                type="button"
                aria-current={isSelected ? 'true' : undefined}
                data-testid={`mention-option-${member.id}`}
                onClick={() => {
                  handleSelect(member);
                }}
                className={`w-full flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all ${
                  isSelected
                    ? 'bg-accent text-accent-foreground font-medium'
                    : 'text-foreground hover:bg-muted/60'
                }`}
              >
                <div
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-white"
                  style={{ backgroundColor: member.colorBadge }}
                >
                  <Bot className="h-4 w-4" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold truncate">
                      {member.name}
                    </span>
                    <span className="rounded bg-muted px-1.5 py-0.2 text-[10px] text-muted-foreground truncate font-medium">
                      {member.role}
                    </span>
                  </div>
                  {member.description ? (
                    <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                      {member.description}
                    </p>
                  ) : null}
                </div>

                {isSelected ? (
                  <Target className="h-3.5 w-3.5 text-primary shrink-0" />
                ) : null}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};
