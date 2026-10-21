'use client';

import React from 'react';
import { Command, Activity } from 'lucide-react';
import { useCommandCenterHudStore } from './useCommandCenterHudStore';

export const CommandCenterQuickTriggerButton: React.FC = () => {
  const { gatewayHealth, toggleHud } = useCommandCenterHudStore();

  const renderHealthIndicator = () => {
    if (gatewayHealth === 'healthy') {
      return (
        <span
          className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"
          title="系统与网关服务连接完好"
        />
      );
    }
    if (gatewayHealth === 'degraded') {
      return (
        <span
          className="w-2 h-2 rounded-full bg-amber-400"
          title="网关存在部分告警或轻度降级"
        />
      );
    }
    return (
      <span
        className="w-2 h-2 rounded-full bg-rose-500"
        title="网关或本地服务离线"
      />
    );
  };

  return (
    <button
      type="button"
      onClick={toggleHud}
      aria-label="打开 Command Center 全局运维大厅"
      className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 text-slate-200 border border-slate-800 hover:border-slate-700 shadow-md transition-all duration-150 select-none group"
      title="全局命令中心 (快捷键: Cmd + . 或 Ctrl + .)"
    >
      <div className="flex items-center space-x-1.5">
        {renderHealthIndicator()}
        <Activity className="w-3.5 h-3.5 text-sky-400 group-hover:rotate-12 transition-transform" aria-hidden="true" />
        <span className="text-xs font-semibold">Command Center</span>
      </div>

      <div className="hidden sm:flex items-center space-x-0.5 px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-400 border border-slate-700/60">
        <Command className="w-2.5 h-2.5" aria-hidden="true" />
        <span>.</span>
      </div>
    </button>
  );
};
