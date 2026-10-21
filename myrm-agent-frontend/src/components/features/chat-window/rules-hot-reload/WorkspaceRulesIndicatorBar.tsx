/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Vector Icons)
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 * - @/components/features/chat-window/rules-hot-reload/useWorkspaceRulesStore
 *
 * [OUTPUT]
 * - WorkspaceRulesIndicatorBar (POS: Top bar indicator component for rules hot-reload and bypass toggle)
 *
 * [POS]
 * Visual status bar for Item 199 (P1): WorkspaceRulesHotReloadAndEventBusSuite.
 * Renders active AGENTS.md / CLAUDE.md status, content hashes, manual /reload triggers,
 * real-time update notifications, and the global rules bypass toggle (--no-context-files).
 */

import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  FileCode,
  X,
  Sliders,
} from 'lucide-react';
import { useWorkspaceRulesStore } from './useWorkspaceRulesStore';

export interface WorkspaceRulesIndicatorBarProps {
  readonly onReload?: () => void;
  readonly className?: string;
}

export const WorkspaceRulesIndicatorBar: React.FC<WorkspaceRulesIndicatorBarProps> = ({
  onReload,
  className = '',
}) => {
  const {
    ruleFiles,
    combinedHash,
    bypassRules,
    isReloading,
    notificationMessage,
    toggleBypassRules,
    reloadRules,
    dismissNotification,
  } = useWorkspaceRulesStore();

  const handleManualReload = async () => {
    await reloadRules('manual_reload');
    if (onReload) {
      onReload();
    }
  };

  const fileCount = ruleFiles.length;

  return (
    <div
      data-testid="workspace-rules-indicator-bar"
      className={`flex flex-col gap-1.5 p-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs text-slate-300 backdrop-blur-sm ${className}`}
    >
      {/* 状态与控制器主栏 */}
      <div className="flex items-center justify-between gap-3">
        {/* 左侧：规则生效状态徽章 */}
        <div className="flex items-center gap-2 min-w-0">
          {bypassRules ? (
            <span
              data-testid="rules-badge-bypass"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800/80 shrink-0"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>已临时绕过项目规则 (裸跑模式)</span>
            </span>
          ) : (
            <span
              data-testid="rules-badge-active"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 shrink-0"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>规则已装配 ({fileCount} 个文件)</span>
            </span>
          )}

          {/* 规则签名与文件列表 */}
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] font-mono text-slate-400 truncate">
            <span data-testid="combined-hash-label" title="规则集合并指纹">
              #{combinedHash}
            </span>
            {fileCount > 0 && (
              <span className="text-slate-600 truncate">
                ({ruleFiles.map((f) => f.filename).join(', ')})
              </span>
            )}
          </div>
        </div>

        {/* 右侧：操作区 */}
        <div className="flex items-center gap-2 shrink-0">
          {/* 临时绕过开关 */}
          <button
            type="button"
            data-testid="btn-toggle-bypass"
            aria-pressed={bypassRules}
            onClick={toggleBypassRules}
            title={bypassRules ? '恢复注入工作区规则' : '临时绕过工作区规则 (--no-context-files)'}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors border ${
              bypassRules
                ? 'bg-amber-900/40 text-amber-200 border-amber-700/80 hover:bg-amber-900/60'
                : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Sliders className="w-3 h-3" />
            <span>{bypassRules ? '恢复规则' : '绕过规则'}</span>
          </button>

          {/* 手动热重载按钮 */}
          <button
            type="button"
            data-testid="btn-reload-rules"
            aria-label="重新加载工作区规则"
            title="免重启重新校验规则文件 (/reload)"
            disabled={isReloading}
            onClick={handleManualReload}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-cyan-950/60 text-cyan-300 border border-cyan-800/60 hover:bg-cyan-900/60 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${isReloading ? 'animate-spin' : ''}`} />
            <span>/reload</span>
          </button>
        </div>
      </div>

      {/* 实时热重载通知气泡 */}
      {notificationMessage && (
        <div
          data-testid="rules-reload-toast"
          className="flex items-center justify-between gap-2 px-2.5 py-1 rounded bg-cyan-950/80 border border-cyan-800/60 text-[11px] text-cyan-200 animate-fadeIn"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <FileCode className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span className="truncate">{notificationMessage}</span>
          </div>

          <button
            type="button"
            data-testid="btn-dismiss-toast"
            aria-label="关闭通知"
            onClick={dismissNotification}
            className="p-0.5 rounded text-cyan-400 hover:text-cyan-100 hover:bg-cyan-900/60 shrink-0"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
};
