'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * Composer @-Mention Suggestion Dropdown for Bot Mode Group Chat.
 * Provides accessible keyboard-driven agent auto-completion with zero emojis.
 */

import React, { useEffect, useState } from 'react';
import { Bot, Sparkles } from 'lucide-react';
import { GroupParticipant } from './groupChatTypes';

interface ComposerMentionDropdownProps {
  participants: GroupParticipant[];
  query: string;
  isOpen: boolean;
  onSelect: (participant: GroupParticipant) => void;
  onClose: () => void;
}

export const ComposerMentionDropdown: React.FC<ComposerMentionDropdownProps> = ({
  participants,
  query,
  isOpen,
  onSelect,
  onClose,
}) => {
  const [selectedIndex, setSelectedIndex] = useState<number>(0);

  // Filter only assistant bots matching query
  const candidates = participants.filter((p) => {
    if (p.role !== 'assistant_bot') {
      return false;
    }
    const q = query.toLowerCase().trim();
    if (!q) {
      return true;
    }
    return (
      p.participant_id.toLowerCase().includes(q) ||
      p.name.toLowerCase().includes(q) ||
      (p.description ?? '').toLowerCase().includes(q)
    );
  });

  useEffect(() => {
    setSelectedIndex(0);
  }, [query, isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (candidates.length > 0 ? (prev + 1) % candidates.length : 0));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) =>
          candidates.length > 0 ? (prev - 1 + candidates.length) % candidates.length : 0
        );
      } else if (e.key === 'Enter') {
        if (candidates.length > 0 && selectedIndex < candidates.length) {
          e.preventDefault();
          onSelect(candidates[selectedIndex]);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, candidates, selectedIndex, onSelect, onClose]);

  if (!isOpen || candidates.length === 0) {
    return null;
  }

  return (
    <div
      role="listbox"
      aria-label="Agent mentions"
      className="absolute bottom-full left-0 mb-2 w-72 rounded-lg border border-slate-700 bg-slate-900/95 p-1 shadow-2xl backdrop-blur-md z-50 text-slate-200"
    >
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-400 border-b border-slate-800">
        <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
        <span>Mention Agent (Bot Mode)</span>
      </div>
      <div className="max-h-48 overflow-y-auto py-1">
        {candidates.map((agent, index) => {
          const isSelected = index === selectedIndex;
          return (
            <button
              key={agent.participant_id}
              role="option"
              aria-selected={isSelected}
              type="button"
              onClick={() => {
                onSelect(agent);
              }}
              className={`w-full flex items-center gap-2.5 px-2.5 py-2 text-left text-xs rounded transition-colors ${
                isSelected
                  ? 'bg-indigo-600/30 text-indigo-200 border border-indigo-500/40'
                  : 'hover:bg-slate-800/60 text-slate-300'
              }`}
            >
              <div
                className="flex h-6 w-6 items-center justify-center rounded-full text-white text-[10px] font-bold shrink-0"
                style={{ backgroundColor: agent.avatar_color }}
              >
                <Bot className="h-3.5 w-3.5" />
              </div>
              <div className="flex-1 truncate">
                <div className="font-medium text-slate-100 flex items-center gap-1">
                  <span>@{agent.name}</span>
                </div>
                {agent.description ? (
                  <div className="text-[10px] text-slate-400 truncate">{agent.description}</div>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
