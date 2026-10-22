'use client';

/**
 * [INPUT]
 * - groupChatTypes: GroupChatRoomHeaderProps, GroupChatBotMember, BotPresenceStatus
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - GroupChatRoomHeader: Fixed top presence header showing multi-agent members and live states
 *
 * [POS]
 * Multi-Agent Group Chat room presence header with live status indicators and skill popovers.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Users,
  Bot,
  Loader2,
  Wrench,
  X,
  Sparkles,
} from 'lucide-react';
import {
  GroupChatRoomHeaderProps,
  GroupChatBotMember,
  BotPresenceStatus,
} from './groupChatTypes';

export const GroupChatRoomHeader: React.FC<GroupChatRoomHeaderProps> = ({
  roomName,
  members,
  onSelectMember,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('groupChat');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests
  }

  const [inspectingMember, setInspectingMember] = useState<GroupChatBotMember | null>(null);

  const getStatusIndicator = (status: BotPresenceStatus) => {
    switch (status) {
      case 'reasoning': {
        return (
          <span
            data-testid="status-indicator-reasoning"
            className="absolute -bottom-0.5 -right-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-blue-500 ring-2 ring-background"
          >
            <Loader2 className="h-2.5 w-2.5 text-white animate-spin" />
          </span>
        );
      }
      case 'idle': {
        return (
          <span
            data-testid="status-indicator-idle"
            className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-emerald-500 ring-2 ring-background"
          />
        );
      }
      case 'pass': {
        return (
          <span
            data-testid="status-indicator-pass"
            className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full bg-muted-foreground/60 ring-2 ring-background"
          />
        );
      }
      default: {
        return null;
      }
    }
  };

  const handleMemberClick = (member: GroupChatBotMember) => {
    setInspectingMember(member);
    if (onSelectMember) {
      onSelectMember(member);
    }
  };

  return (
    <div
      data-testid="group-chat-room-header"
      className={`border-b border-border/80 bg-background/95 px-4 py-2.5 backdrop-blur-md shadow-sm ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        {/* Left Room Info */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            <Users className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-foreground truncate">
              {roomName}
            </h3>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1">
              <span>{members.length}</span>
              <span>{t('presence.membersOnline')}</span>
            </p>
          </div>
        </div>

        {/* Right Members Avatars presence row */}
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          {members.map((member) => (
            <button
              key={member.id}
              type="button"
              data-testid={`member-avatar-${member.id}`}
              onClick={() => {
                handleMemberClick(member);
              }}
              title={`${member.name} (${member.role})`}
              className="group relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/80 bg-card text-foreground transition-all hover:scale-105 hover:border-primary/60 active:scale-95"
            >
              <Bot className="h-4 w-4" style={{ color: member.colorBadge }} />
              {getStatusIndicator(member.status)}
            </button>
          ))}
        </div>
      </div>

      {/* Member Skill & Details Floating Drawer / Modal */}
      {inspectingMember ? (
        <div
          data-testid="member-inspect-panel"
          className="mt-2.5 rounded-2xl border border-border/80 bg-card/95 p-3.5 shadow-md animate-in fade-in duration-150"
        >
          <div className="flex items-start justify-between gap-2 border-b border-border/50 pb-2">
            <div className="flex items-center gap-2">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-lg border text-white font-bold text-xs"
                style={{ backgroundColor: inspectingMember.colorBadge }}
              >
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <span>{inspectingMember.name}</span>
                  <span className="rounded-full bg-secondary/80 px-2 py-0.5 text-[10px] font-medium text-secondary-foreground">
                    {inspectingMember.role}
                  </span>
                </h4>
                {inspectingMember.description ? (
                  <p className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
                    {inspectingMember.description}
                  </p>
                ) : null}
              </div>
            </div>

            <button
              type="button"
              aria-label="关闭"
              onClick={() => {
                setInspectingMember(null);
              }}
              className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="mt-2 space-y-1.5">
            <div className="flex items-center gap-1 text-[11px] font-semibold text-muted-foreground">
              <Wrench className="h-3 w-3" />
              <span>{t('presence.skillsTitle')}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {inspectingMember.skills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-muted/40 px-2 py-0.5 text-[10px] font-mono text-foreground"
                >
                  <Sparkles className="h-2.5 w-2.5 text-primary" />
                  <span>{skill}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
