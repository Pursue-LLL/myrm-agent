import React from 'react';
import { Bot, Sparkles, Cpu, Check, Activity } from 'lucide-react';
import { useErgonomicCockpitStore } from './useErgonomicCockpitStore';
import type { AgentWaveformState } from './ergonomicCockpitTypes';

interface InlinePersonaAvatarProps {
  agentName?: string;
  baseModel?: string;
  state?: AgentWaveformState;
  className?: string;
}

export const InlinePersonaAvatar: React.FC<InlinePersonaAvatarProps> = ({
  agentName,
  baseModel,
  state: propState,
  className = '',
}) => {
  const { activePersona } = useErgonomicCockpitStore();

  const name = agentName ?? activePersona.name;
  const model = baseModel ?? activePersona.baseModel;
  const state = propState ?? activePersona.state;

  const renderStateWaveform = (): React.ReactElement => {
    switch (state) {
      case 'thinking':
        return (
          <div className="flex items-end gap-0.5 h-3 px-1 py-0.5 rounded bg-amber-500/10 border border-amber-500/20" title="正在深度推演与思考">
            <span className="w-0.5 h-2 bg-amber-400 animate-pulse" />
            <span className="w-0.5 h-3 bg-amber-400 animate-pulse [animation-delay:150ms]" />
            <span className="w-0.5 h-1.5 bg-amber-400 animate-pulse [animation-delay:300ms]" />
          </div>
        );

      case 'tool_executing':
        return (
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/10 border border-sky-500/20 text-[10px] text-sky-400 font-mono" title="正在调度外部沙箱工具">
            <Activity className="w-2.5 h-2.5 animate-spin" />
            <span>TOOL</span>
          </div>
        );

      case 'streaming':
        return (
          <div className="flex items-end gap-0.5 h-3 px-1 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20" title="高帧率流式生成中">
            <span className="w-0.5 h-1 bg-emerald-400 animate-bounce" />
            <span className="w-0.5 h-2.5 bg-emerald-400 animate-bounce [animation-delay:100ms]" />
            <span className="w-0.5 h-2 bg-emerald-400 animate-bounce [animation-delay:200ms]" />
          </div>
        );

      case 'completed':
        return (
          <div className="flex items-center gap-0.5 px-1 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px]">
            <Check className="w-2.5 h-2.5" />
          </div>
        );

      default:
        return (
          <div className="w-1.5 h-1.5 rounded-full bg-slate-500" title="空闲就绪" />
        );
    }
  };

  return (
    <div
      aria-label={`内联智能体身份与状态波形: ${name}`}
      className={`inline-flex items-center gap-2 select-none ${className}`}
    >
      <div className="relative shrink-0">
        <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shadow-sm">
          <Bot className="w-4 h-4" />
        </div>
        <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-slate-900 bg-sky-400" />
      </div>

      <div className="flex items-center gap-1.5">
        <span className="text-xs font-semibold text-white tracking-tight">{name}</span>
        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 border border-slate-700">
          {model}
        </span>
        {renderStateWaveform()}
      </div>
    </div>
  );
};
