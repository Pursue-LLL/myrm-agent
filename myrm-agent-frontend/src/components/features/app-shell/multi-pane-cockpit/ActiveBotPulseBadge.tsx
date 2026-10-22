import React from 'react';
import { Clock, Cpu, Sparkles, Bot, Shield, BookOpen, MessageSquare, TrendingUp } from 'lucide-react';
import type { BotPulseStatus } from './multiPaneCockpitTypes';

interface ActiveBotPulseBadgeProps {
  pulse: BotPulseStatus;
  avatarIconName?: string;
  size?: 'sm' | 'md' | 'lg';
}

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  MessageSquare,
  BookOpen,
  Shield,
  TrendingUp,
};

export const ActiveBotPulseBadge: React.FC<ActiveBotPulseBadgeProps> = ({
  pulse,
  avatarIconName,
  size = 'md',
}) => {
  const IconComponent = (avatarIconName && ICON_MAP[avatarIconName]) ? ICON_MAP[avatarIconName] : Bot;
  const isActive = pulse.isActive;

  const sizeClasses = {
    sm: 'h-8 w-8',
    md: 'h-10 w-10',
    lg: 'h-12 w-12',
  }[size];

  const iconSizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-5 w-5',
    lg: 'h-6 w-6',
  }[size];

  return (
    <div className="relative inline-flex items-center justify-center shrink-0">
      {isActive && (
        <span
          className={`absolute inset-0 rounded-full animate-ping opacity-35 ${
            pulse.activityType === 'active_cron'
              ? 'bg-amber-400'
              : pulse.activityType === 'active_thinking'
              ? 'bg-purple-400'
              : 'bg-blue-400'
          }`}
        />
      )}

      <div
        className={`relative flex items-center justify-center rounded-full border transition-all ${sizeClasses} ${
          isActive
            ? pulse.activityType === 'active_cron'
              ? 'border-amber-400/80 bg-amber-950/40 text-amber-300 shadow-[0_0_12px_rgba(251,191,36,0.25)]'
              : pulse.activityType === 'active_thinking'
              ? 'border-purple-400/80 bg-purple-950/40 text-purple-300 shadow-[0_0_12px_rgba(192,132,252,0.25)]'
              : 'border-blue-400/80 bg-blue-950/40 text-blue-300 shadow-[0_0_12px_rgba(96,165,250,0.25)]'
            : 'border-slate-700 bg-slate-800 text-slate-400'
        }`}
      >
        <IconComponent className={iconSizeClasses} />

        {isActive && (
          <span
            className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border border-slate-900 bg-slate-800 shadow"
            title={pulse.currentTaskTitle ?? '活跃执行中'}
          >
            {pulse.activityType === 'active_cron' && (
              <Clock className="h-2.5 w-2.5 text-amber-400 animate-spin" />
            )}
            {pulse.activityType === 'active_thinking' && (
              <Sparkles className="h-2.5 w-2.5 text-purple-400 animate-pulse" />
            )}
            {pulse.activityType === 'active_tool_exec' && (
              <Cpu className="h-2.5 w-2.5 text-blue-400 animate-spin" />
            )}
          </span>
        )}
      </div>
    </div>
  );
};
