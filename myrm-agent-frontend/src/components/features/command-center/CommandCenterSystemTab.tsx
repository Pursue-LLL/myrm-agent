import React from 'react';
import {
  Activity,
  Server,
  Wifi,
  RefreshCw,
  AlertTriangle,
  ShieldCheck,
  Filter,
} from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';
import { LogComponent } from './commandCenterTypes';

export const CommandCenterSystemTab: React.FC = () => {
  const {
    health,
    logs,
    selectedLogComponent,
    setSelectedLogComponent,
  } = useCommandCenterStore();

  const filteredLogs = logs.filter((log) => {
    if (selectedLogComponent === 'all') {
      return true;
    }
    return log.component === selectedLogComponent;
  });

  const filterOptions: Array<{ id: LogComponent | 'all'; label: string }> = [
    { id: 'all', label: '全部组件' },
    { id: 'gateway', label: 'Gateway 网关' },
    { id: 'agent', label: 'Agent 智能体' },
    { id: 'error', label: 'Error 异常' },
    { id: 'desktop', label: 'Desktop 客户端' },
  ];

  return (
    <div
      data-testid="command-center-system-tab"
      className="flex flex-col h-[460px] select-none text-slate-200"
    >
      {/* 顶部网关健康体态卡片 */}
      <div className="grid grid-cols-4 gap-2.5 mb-3">
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>网关体态</span>
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            <Server className="w-4 h-4 text-emerald-400" />
            <span className="font-bold text-sm text-slate-100">运行正常</span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono mt-0.5">
            {health.serverType}
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-slate-400 text-[11px]">WS 延迟</div>
          <div className="mt-1 flex items-center gap-1.5">
            <Wifi className="w-4 h-4 text-indigo-400" />
            <span className="font-bold text-sm text-slate-100">
              {health.latencyMs} ms
            </span>
          </div>
          <span className="text-[10px] text-emerald-400 font-mono mt-0.5">极速响应</span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-slate-400 text-[11px]">内核版本</div>
          <div className="mt-1 flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-amber-400" />
            <span className="font-bold text-xs text-slate-100 font-mono">
              {health.version}
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono mt-0.5">无版本偏移</span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 flex flex-col justify-between">
          <div className="text-slate-400 text-[11px]">活跃并发会话</div>
          <div className="mt-1 flex items-center gap-1.5">
            <Activity className="w-4 h-4 text-sky-400" />
            <span className="font-bold text-sm text-slate-100">
              {health.activeSessionsCount}
            </span>
          </div>
          <span className="text-[10px] text-slate-500 font-mono mt-0.5">会话隔离</span>
        </div>
      </div>

      {/* 日志过滤栏 */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-xs">
        <div className="flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-slate-500" />
          <span className="text-slate-400 text-[11px]">日志过滤：</span>
          <div className="flex items-center gap-1 bg-slate-900 p-0.5 rounded-lg border border-slate-800">
            {filterOptions.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setSelectedLogComponent(opt.id)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  selectedLogComponent === opt.id
                    ? 'bg-slate-800 text-indigo-400'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <span className="text-[10px] text-slate-500 font-mono">
          共 {filteredLogs.length} 条实时事件
        </span>
      </div>

      {/* 实时聚合日志终端视窗 */}
      <div className="flex-1 overflow-y-auto bg-slate-950 rounded-xl p-3 border border-slate-800 font-mono text-[11px] space-y-1.5">
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-600">
            <span>当前筛选条件下暂无日志</span>
          </div>
        ) : (
          filteredLogs.map((log) => {
            const levelColor =
              log.level === 'error'
                ? 'text-rose-400'
                : log.level === 'warn'
                ? 'text-amber-400'
                : log.level === 'debug'
                ? 'text-slate-500'
                : 'text-sky-400';

            return (
              <div
                key={log.id}
                className="flex items-start gap-2 hover:bg-slate-900/50 p-1 rounded transition-colors"
              >
                <span className="text-slate-500 shrink-0">[{log.timestamp}]</span>
                <span className={`font-bold shrink-0 ${levelColor}`}>
                  [{log.level.toUpperCase()}]
                </span>
                <span className="text-indigo-400 shrink-0">[{log.component}]</span>
                <span className="text-slate-300 break-all">{log.message}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
