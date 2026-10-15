import React from 'react';
import {
  Terminal,
  AlertCircle,
  AlertTriangle,
  Info,
  Wrench,
  Trash2,
  X,
} from 'lucide-react';
import { useThreeJsSandboxStore } from './useThreeJsSandboxStore';
import { WebGLLogEntry, WebGLSelfHealingDossier } from './threeJsTypes';
import { buildWebGLSelfHealingDossier } from './threeJsSandboxEngine';

interface ThreeJsConsoleDrawerProps {
  onSelfHealingTriggered?: (dossier: WebGLSelfHealingDossier) => void;
}

export const ThreeJsConsoleDrawer: React.FC<ThreeJsConsoleDrawerProps> = ({
  onSelfHealingTriggered,
}) => {
  const {
    sceneId,
    logs,
    metrics,
    isConsoleOpen,
    toggleConsole,
    clearLogs,
  } = useThreeJsSandboxStore();

  if (!isConsoleOpen) {
    return null;
  }

  const latestError = logs.find((l) => l.level === 'error');

  const handleSelfHealing = (errorEntry: WebGLLogEntry) => {
    const dossier = buildWebGLSelfHealingDossier(sceneId, errorEntry, metrics);
    if (onSelfHealingTriggered) {
      onSelfHealingTriggered(dossier);
    }
  };

  const getLogIcon = (level: WebGLLogEntry['level']) => {
    switch (level) {
      case 'error':
        return <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />;
      case 'warn':
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />;
      default:
        return <Info className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />;
    }
  };

  return (
    <section
      data-testid="threejs-console-drawer"
      aria-label="WebGL 运行时自检控制台"
      className="absolute bottom-0 left-0 right-0 z-30 max-h-64 bg-slate-950/95 backdrop-blur-md border-t border-slate-800 text-xs flex flex-col shadow-2xl transition-all"
    >
      {/* 控制台顶栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-900/60">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-slate-200">
            WebGL 运行时自检控制台
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-400">
            {logs.length} 条记录
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {latestError && (
            <button
              type="button"
              onClick={() => handleSelfHealing(latestError)}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition-colors shadow-xs"
              title="将报错信息格式化并反哺给 Agent 自动修复代码"
            >
              <Wrench className="w-3 h-3" />
              <span>一键 Agent 自愈</span>
            </button>
          )}

          <button
            type="button"
            onClick={clearLogs}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="清空控制台日志"
            aria-label="清空日志"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={toggleConsole}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="关闭控制台"
            aria-label="关闭控制台"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 日志内容滚动列表 */}
      <div className="p-3 overflow-y-auto space-y-2 flex-1 font-mono text-[11px]">
        {logs.length === 0 ? (
          <div className="text-slate-500 py-4 text-center">
            暂无 WebGL 报错或警告，运行时状态正常
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className={`flex items-start gap-2 p-2 rounded-lg border leading-tight ${
                log.level === 'error'
                  ? 'bg-rose-950/30 border-rose-900/50 text-rose-300'
                  : log.level === 'warn'
                  ? 'bg-amber-950/20 border-amber-900/40 text-amber-300'
                  : 'bg-slate-900/60 border-slate-800 text-slate-300'
              }`}
            >
              {getLogIcon(log.level)}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between text-[10px] text-slate-500 mb-0.5">
                  <span className="uppercase">{log.source || 'runtime'}</span>
                  <span>{log.timestamp}</span>
                </div>
                <p className="whitespace-pre-wrap break-all">{log.message}</p>
                {log.shaderInfo && (
                  <pre className="mt-1 p-1.5 rounded bg-black/40 text-[10px] text-rose-400 overflow-x-auto border border-rose-900/40">
                    {log.shaderInfo.infoLog}
                  </pre>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
};
