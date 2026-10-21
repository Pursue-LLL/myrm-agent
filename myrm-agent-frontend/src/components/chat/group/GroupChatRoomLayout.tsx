'use client';

/**
 * GroupChatRoomLayout Component.
 * Discord/Slack-style multi-bot group workspace for collaborative swarms.
 * Implements Bot Mode orchestration and @-mention routing with zero emojis.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Hash, Send, Shield, Sparkles, User } from 'lucide-react';
import {
  GroupMessage,
  GroupParticipant,
  GroupRoom,
  PeerSessionArchive,
} from './groupChatTypes';
import { groupChatService } from './groupChatService';
import { ComposerMentionDropdown } from './ComposerMentionDropdown';
import { GroupRoomSidebar } from './GroupRoomSidebar';

interface GroupChatRoomLayoutProps {
  initialRoomId?: string;
}

export const GroupChatRoomLayout: React.FC<GroupChatRoomLayoutProps> = ({
  initialRoomId,
}) => {
  // Safe translation fallback
  let t = (key: string): string => key;
  try {
    const translator = useTranslations('groupChat');
    t = (key: string) => translator(key);
  } catch {
    // Fallback when outside next-intl context in tests
  }

  const [room, setRoom] = useState<GroupRoom | null>(null);
  const [peerArchives, setPeerArchives] = useState<PeerSessionArchive[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isMentionOpen, setIsMentionOpen] = useState<boolean>(false);
  const [mentionQuery, setMentionQuery] = useState<string>('');
  const [mentionedAgents, setMentionedAgents] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    try {
      if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
      }
    } catch {
      // Ignored in test / headless environments
    }
  }, []);

  const loadRoomData = useCallback(async () => {
    const rooms = await groupChatService.listRooms();
    const activeRoom = initialRoomId
      ? rooms.find((r) => r.room_id === initialRoomId) || rooms[0]
      : rooms[0];

    if (activeRoom) {
      setRoom(activeRoom);
      const archives = await groupChatService.listPeerArchives('code_architect');
      setPeerArchives(archives);
    }
  }, [initialRoomId]);

  useEffect(() => {
    loadRoomData();
  }, [loadRoomData]);

  useEffect(() => {
    scrollToBottom();
  }, [room?.messages, scrollToBottom]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const text = e.target.value;
    setInputValue(text);

    const atIndex = text.lastIndexOf('@');
    if (atIndex !== -1 && atIndex >= text.length - 15) {
      const query = text.slice(atIndex + 1);
      if (!query.includes(' ')) {
        setMentionQuery(query);
        setIsMentionOpen(true);
        return;
      }
    }
    setIsMentionOpen(false);
  };

  const handleSelectMention = (participant: GroupParticipant) => {
    const atIndex = inputValue.lastIndexOf('@');
    if (atIndex !== -1) {
      const prefix = inputValue.slice(0, atIndex);
      const newText = `${prefix}@${participant.name} `;
      setInputValue(newText);
      if (!mentionedAgents.includes(participant.participant_id)) {
        setMentionedAgents((prev) => [...prev, participant.participant_id]);
      }
    }
    setIsMentionOpen(false);
    inputRef.current?.focus();
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || !room || isSubmitting) {
      return;
    }

    const content = inputValue.trim();
    setIsSubmitting(true);

    // Extract all mentions from text and selection
    const targetAgents: string[] = [];
    for (const p of room.participants) {
      if (p.role === 'assistant_bot') {
        const isMentioned =
          content.includes(`@${p.name}`) ||
          content.includes(`@${p.participant_id}`) ||
          mentionedAgents.includes(p.participant_id);
        if (isMentioned && !targetAgents.includes(p.participant_id)) {
          targetAgents.push(p.participant_id);
        }
      }
    }

    try {
      const newMsgs = await groupChatService.postMessage(room.room_id, {
        sender_id: 'user_me',
        content,
        mentioned_agent_ids: targetAgents,
      });

      setRoom((prev) => {
        if (!prev) {
          return null;
        }
        return {
          ...prev,
          messages: [...prev.messages, ...newMsgs],
        };
      });

      setInputValue('');
      setMentionedAgents([]);
      setIsMentionOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!room) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-950 text-slate-400">
        Loading multi-bot workspace...
      </div>
    );
  }

  return (
    <div className="flex h-full w-full bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Center Main Room Chat */}
      <main className="flex-1 flex flex-col min-w-0 h-full border-r border-slate-800">
        {/* Header */}
        <header className="h-14 border-b border-slate-800 px-6 flex items-center justify-between bg-slate-900/40">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Hash className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="font-semibold text-sm text-slate-100 truncate">{room.name}</h1>
                <span className="flex items-center gap-1 rounded bg-indigo-950/60 border border-indigo-700/50 px-1.5 py-0.5 text-[10px] text-indigo-300 font-mono">
                  <Shield className="h-2.5 w-2.5" />
                  Bot Mode
                </span>
              </div>
              <p className="text-xs text-slate-400 truncate">{room.topic}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Sparkles className="h-3.5 w-3.5 text-amber-400" />
            <span>Hermes Parity</span>
          </div>
        </header>

        {/* Messages Timeline */}
        <section
          aria-label="Room message timeline"
          className="flex-1 overflow-y-auto p-6 space-y-4"
        >
          {room.messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 text-xs">
              <Bot className="h-8 w-8 text-slate-400 mb-2" />
              <p>{t('noMessages')}</p>
            </div>
          ) : (
            room.messages.map((msg: GroupMessage) => {
              const isHuman = msg.sender_role === 'human';
              const sender = room.participants.find(
                (p) => p.participant_id === msg.sender_id
              );
              const avatarColor = sender?.avatar_color || (isHuman ? '#0f172a' : '#6366f1');

              return (
                <div key={msg.message_id} className="flex gap-3.5 group">
                  <div
                    className="flex h-8 w-8 items-center justify-center rounded-full text-white text-xs font-bold shrink-0 shadow-md"
                    style={{ backgroundColor: avatarColor }}
                  >
                    {isHuman ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs font-semibold text-slate-200">
                        {msg.sender_name}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {new Date(msg.timestamp_epoch_ms).toLocaleTimeString()}
                      </span>
                      {isHuman ? (
                        <span className="text-[9px] px-1 bg-slate-800 text-slate-400 rounded">
                          Human
                        </span>
                      ) : (
                        <span className="text-[9px] px-1 bg-indigo-950 text-indigo-300 border border-indigo-800 rounded">
                          Bot
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-slate-300 leading-relaxed bg-slate-900/60 p-3 rounded-lg border border-slate-800/80">
                      {msg.content}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          <div ref={messagesEndRef} />
        </section>

        {/* Message Composer */}
        <footer className="p-4 border-t border-slate-800 bg-slate-900/40 relative">
          <ComposerMentionDropdown
            participants={room.participants}
            query={mentionQuery}
            isOpen={isMentionOpen}
            onSelect={handleSelectMention}
            onClose={() => {
              setIsMentionOpen(false);
            }}
          />
          <form
            data-testid="group-chat-composer-form"
            onSubmit={handleSendMessage}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={handleInputChange}
              placeholder={t('composerPlaceholder')}
              className="flex-1 bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-2.5 text-xs text-slate-100 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isSubmitting}
              className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-400 text-white text-xs font-medium px-4 py-2.5 rounded-lg transition-colors shrink-0"
            >
              <Send className="h-3.5 w-3.5" />
              <span>{t('sendBtn')}</span>
            </button>
          </form>
        </footer>
      </main>

      {/* Right Sidebar */}
      <GroupRoomSidebar
        participants={room.participants}
        peerArchives={peerArchives}
      />
    </div>
  );
};
