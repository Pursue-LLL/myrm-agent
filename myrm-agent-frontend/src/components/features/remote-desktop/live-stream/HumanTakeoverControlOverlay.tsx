import React from 'react';
import {
  AlertTriangle,
  Key,
  ShieldCheck,
  X,
  UserCheck,
} from 'lucide-react';
import { useRemoteDesktopStore } from './useRemoteDesktopStore';

export const HumanTakeoverControlOverlay: React.FC = () => {
  const {
    controlMode,
    isTakeoverAlertActive,
    takeoverReason,
    requestHumanTakeover,
    releaseHumanTakeover,
  } = useRemoteDesktopStore();

  if (!isTakeoverAlertActive && controlMode !== 'human-takeover') {
    return null;
  }

  const isTakeover = controlMode === 'human-takeover';

  return (
    <aside
      aria-label="双向人工接管与安全审计条"
      className="w-full bg-slate-900/95 border border-amber-500/40 rounded-lg p-3 text-slate-100 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 backdrop-blur-md transition-all"
      data-testid="human-takeover-control-overlay"
    >
      <div className="flex items-center space-x-3">
        <div className="p-2 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
          <AlertTriangle className="w-4 h-4" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-xs text-white">
              {isTakeover ? '您当前正在人工接管中' : 'AI 请求人工介入接管'}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 font-medium border border-amber-800/60">
              {isTakeover ? '控制权锁定' : '等待响应'}
            </span>
          </div>
          <p className="text-[11px] text-slate-300 mt-0.5">
            {takeoverReason || '检测到需要人工确认的敏感验证码或高危操作'}
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-2 self-end sm:self-auto shrink-0">
        {isTakeover ? (
          <button
            type="button"
            onClick={releaseHumanTakeover}
            aria-label="确认完成并交回 Agent 自动执行"
            className="px-3 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>完成并交还 Agent</span>
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => requestHumanTakeover()}
              aria-label="立即接管控制权"
              className="px-3 py-1.5 text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all"
            >
              <Key className="w-3.5 h-3.5" />
              <span>立即接管</span>
            </button>
            <button
              type="button"
              onClick={releaseHumanTakeover}
              aria-label="忽略介入请求并让 Agent 继续"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </>
        )}
      </div>
    </aside>
  );
};
