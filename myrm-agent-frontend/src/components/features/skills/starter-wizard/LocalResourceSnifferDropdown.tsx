import React from 'react';
import { RefreshCw, Sparkles, Users, Clock, ShieldCheck } from 'lucide-react';
import type { SniffedResource } from './starterWizardTypes';

interface LocalResourceSnifferDropdownProps {
  label: string;
  description: string;
  resources: SniffedResource[];
  selectedResourceId: string;
  isSniffing: boolean;
  onSelectResource: (id: string) => void;
  onRefresh: () => void;
}

export const LocalResourceSnifferDropdown: React.FC<LocalResourceSnifferDropdownProps> = ({
  label,
  description,
  resources,
  selectedResourceId,
  isSniffing,
  onSelectResource,
  onRefresh,
}) => {
  const selectedResource = resources.find((r) => r.id === selectedResourceId);

  return (
    <div className="space-y-2 rounded-lg border border-slate-700/60 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-1.5">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          <span className="text-xs font-semibold text-slate-200">{label}</span>
          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">
            受控本地嗅探
          </span>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isSniffing}
          className="inline-flex items-center space-x-1 rounded px-2 py-1 text-[11px] text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-50"
          aria-label="刷新受控嗅探候选"
        >
          <RefreshCw className={`h-3 w-3 ${isSniffing ? 'animate-spin text-blue-400' : ''}`} />
          <span>{isSniffing ? '嗅探中...' : '重新嗅探'}</span>
        </button>
      </div>

      <p className="text-[11px] text-slate-400">{description}</p>

      <div className="relative">
        <label htmlFor="resource-sniffer-select" className="sr-only">
          {label}
        </label>
        <select
          id="resource-sniffer-select"
          value={selectedResourceId}
          onChange={(e) => {
            onSelectResource(e.target.value);
          }}
          className="w-full rounded-md border border-slate-700 bg-slate-800/90 px-3 py-2 text-xs text-slate-100 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {resources.map((resource) => (
            <option key={resource.id} value={resource.id}>
              {resource.name} {resource.isRecommended ? '（推荐活跃）' : ''}
            </option>
          ))}
        </select>
      </div>

      {selectedResource && (
        <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-slate-400">
          {selectedResource.isRecommended && (
            <span className="inline-flex items-center space-x-1 text-amber-300">
              <Sparkles className="h-3 w-3" />
              <span>智能推荐目标</span>
            </span>
          )}
          {selectedResource.memberCount !== undefined && (
            <span className="inline-flex items-center space-x-1">
              <Users className="h-3 w-3 text-slate-400" />
              <span>{selectedResource.memberCount} 位群成员</span>
            </span>
          )}
          {selectedResource.lastActiveTime && (
            <span className="inline-flex items-center space-x-1">
              <Clock className="h-3 w-3 text-slate-400" />
              <span>最近发言: {selectedResource.lastActiveTime}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
};
