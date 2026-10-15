import React from 'react';
import { MessageSquarePlus, Sparkles } from 'lucide-react';
import { useSideChatStore } from './useSideChatStore';

export interface SideChatTriggerButtonProps {
  className?: string;
}

export const SideChatTriggerButton: React.FC<SideChatTriggerButtonProps> = ({
  className = '',
}) => {
  const { isOpen, unreadCount, steeringQueue, setOpen } = useSideChatStore();

  const pendingCount = steeringQueue.filter((i) => i.status === 'pending').length;

  return (
    <button
      type="button"
      data-testid="side-chat-trigger-button"
      onClick={() => {
        setOpen(!isOpen);
      }}
      title="展开平行支线对话抽屉 (随时补充需求，不打断主任务)"
      className={`relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all border shadow-sm ${
        isOpen
          ? 'bg-indigo-600 text-white border-indigo-500 shadow-indigo-600/30'
          : 'bg-zinc-900/90 hover:bg-zinc-800 text-zinc-200 border-zinc-750 hover:border-zinc-700'
      } ${className}`}
    >
      <MessageSquarePlus className="w-3.5 h-3.5 text-indigo-400" />
      <span>支线对话</span>

      {pendingCount > 0 ? (
        <span className="flex items-center gap-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40">
          <Sparkles className="w-2.5 h-2.5" />
          {pendingCount}
        </span>
      ) : unreadCount > 0 ? (
        <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-indigo-500 text-white">
          {unreadCount}
        </span>
      ) : null}
    </button>
  );
};
