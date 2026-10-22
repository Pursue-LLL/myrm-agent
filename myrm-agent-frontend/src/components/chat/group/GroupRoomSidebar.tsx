'use client';

/**
 * Sidebar Panel for Group Room: Participants & Canonical Peer Inbox.
 * Zero-emoji design with accessible SVG badges.
 */

import React from 'react';
import { Bot, Inbox, Lock, User, Users } from 'lucide-react';
import { GroupParticipant, PeerSessionArchive } from './groupChatTypes';

interface GroupRoomSidebarProps {
  participants: GroupParticipant[];
  peerArchives: PeerSessionArchive[];
  onSelectPeerArchive?: (archive: PeerSessionArchive) => void;
}

export const GroupRoomSidebar: React.FC<GroupRoomSidebarProps> = ({
  participants,
  peerArchives,
  onSelectPeerArchive,
}) => {
  return (
    <aside
      aria-label="Room Participants and Peer Inbox"
      className="w-64 border-l border-slate-800 bg-slate-900/60 p-4 flex flex-col gap-6 overflow-y-auto"
    >
      {/* Participants Section */}
      <div>
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          <Users className="h-3.5 w-3.5 text-indigo-400" />
          <span>Room Participants ({participants.length})</span>
        </div>
        <div className="space-y-2">
          {participants.map((p) => {
            const isHuman = p.role === 'human';
            return (
              <div
                key={p.participant_id}
                className="flex items-center gap-2.5 p-2 rounded-lg bg-slate-800/40 border border-slate-700/50 hover:bg-slate-800/70 transition-colors"
              >
                <div
                  className="flex h-7 w-7 items-center justify-center rounded-full text-white text-xs font-bold shrink-0 shadow-sm"
                  style={{ backgroundColor: p.avatar_color }}
                >
                  {isHuman ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-200 truncate">{p.name}</span>
                    {p.is_avatar_locked ? (
                      <Lock
                        className="h-2.5 w-2.5 text-slate-400 shrink-0"
                        aria-label="Avatar Locked"
                      />
                    ) : null}
                  </div>
                  <div className="text-[10px] text-slate-400 truncate">
                    {isHuman ? 'Human Operator' : `@${p.participant_id}`}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Canonical Peer DM Archives Section */}
      <div className="flex-1">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          <Inbox className="h-3.5 w-3.5 text-emerald-400" />
          <span>Canonical Peer Inbox</span>
        </div>
        {peerArchives.length === 0 ? (
          <div className="text-xs text-slate-400 italic p-2 bg-slate-800/20 rounded border border-slate-800">
            No peer dialogues archived
          </div>
        ) : (
          <div className="space-y-2">
            {peerArchives.map((archive) => (
              <button
                key={archive.canonical_chat_id}
                type="button"
                onClick={() => {
                  if (onSelectPeerArchive) {
                    onSelectPeerArchive(archive);
                  }
                }}
                className="w-full text-left p-2 rounded-lg bg-slate-800/30 border border-slate-700/40 hover:border-indigo-500/50 hover:bg-slate-800/60 transition-colors"
              >
                <div className="flex items-center justify-between text-xs text-slate-200 font-medium">
                  <span className="truncate">{archive.peer_agent_name}</span>
                  <span className="text-[10px] text-indigo-400 font-mono">
                    {archive.message_count} msgs
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 truncate mt-0.5">
                  {archive.last_message}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
};
