import React, { useState } from 'react';
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Flame,
  Globe,
  RotateCcw,
  ShieldAlert,
  Trash2,
  Wand2,
} from 'lucide-react';
import { useSandboxDualViewportStore } from './useSandboxDualViewportStore';

interface ConsoleZeroToleranceHUDProps {
  className?: string;
}

export const ConsoleZeroToleranceHUD: React.FC<ConsoleZeroToleranceHUDProps> = ({
  className = '',
}) => {
  const {
    consoleErrors,
    networkAnomalies,
    healingCycle,
    clearConsoleLogs,
    clearNetworkAnomalies,
    triggerSelfHealing,
    advanceHealingIteration,
    markHealingSuccess,
  } = useSandboxDualViewportStore();

  const [activeTab, setActiveTab] = useState<'console' | 'network'>('console');
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  const totalErrors = consoleErrors.length + networkAnomalies.length;
  const isAllClean = totalErrors === 0 && healingCycle.status !== 'healing_prompt_injected';

  const renderStatusBadge = (): React.ReactElement => {
    switch (healingCycle.status) {
      case 'healing_prompt_injected':
        return (
          <span className="flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 text-[11px] font-mono text-amber-400 border border-amber-500/20 animate-pulse">
            <Flame className="w-3 h-3" />
            <span>自愈提示已注入 · 迭代 {healingCycle.iteration}/{healingCycle.maxIterations}</span>
          </span>
        );
      case 'recompiling':
        return (
          <span className="flex items-center gap-1 rounded bg-sky-500/10 px-2 py-0.5 text-[11px] font-mono text-sky-400 border border-sky-500/20">
            <RotateCcw className="w-3 h-3 animate-spin" />
            <span>沙箱重新编译热重载中...</span>
          </span>
        );
      case 'healed_verified':
        return (
          <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" />
            <span>双视口自愈验证通过 · 零错误白屏</span>
          </span>
        );
      case 'healing_exhausted':
        return (
          <span className="flex items-center gap-1 rounded bg-rose-500/10 px-2 py-0.5 text-[11px] font-mono text-rose-400 border border-rose-500/20">
            <ShieldAlert className="w-3 h-3" />
            <span>自愈次数耗尽 · 需人类介入审查</span>
          </span>
        );
      default:
        if (isAllClean) {
          return (
            <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[11px] font-mono text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 className="w-3 h-3" />
              <span>控制台门禁清洁 (Zero Error & 404)</span>
            </span>
          );
        }
        return (
          <span className="flex items-center gap-1 rounded bg-rose-500/10 px-2 py-0.5 text-[11px] font-mono text-rose-400 border border-rose-500/20">
            <AlertTriangle className="w-3 h-3" />
            <span>拦截到 {totalErrors} 处隐性异常</span>
          </span>
        );
    }
  };

  return (
    <section
      aria-label="控制台与网络请求零容忍门禁"
      className={`border-t border-slate-800 bg-slate-900/95 backdrop-blur-md flex flex-col transition-all ${className}`}
    >
      {/* 头部控制栏 */}
      <div className="flex h-10 items-center justify-between px-3 border-b border-slate-800/80 text-xs">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setIsExpanded(!isExpanded);
            }}
            className="flex items-center gap-1 text-slate-300 hover:text-white font-medium"
            aria-label={isExpanded ? '收起门禁详情' : '展开门禁详情'}
          >
            {isExpanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            <span>控制台零容忍门禁</span>
          </button>
          {renderStatusBadge()}
        </div>

        <div className="flex items-center gap-2">
          {/* 原地自愈动作按键 */}
          {totalErrors > 0 && (
            <button
              type="button"
              onClick={() => {
                triggerSelfHealing();
              }}
              className="flex items-center gap-1 rounded bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-indigo-500 shadow-sm transition-colors"
              aria-label="触发原地视觉与控制台自愈"
            >
              <Wand2 className="w-3 h-3" />
              <span>原地自愈修正</span>
            </button>
          )}

          {healingCycle.status === 'healing_prompt_injected' && (
            <button
              type="button"
              onClick={() => {
                advanceHealingIteration();
              }}
              className="flex items-center gap-1 rounded bg-slate-800 border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:text-white transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              <span>下一步重编译</span>
            </button>
          )}

          {healingCycle.status === 'recompiling' && (
            <button
              type="button"
              onClick={() => {
                markHealingSuccess();
              }}
              className="flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-500 shadow-sm transition-colors"
            >
              <CheckCircle2 className="w-3 h-3" />
              <span>验证全绿</span>
            </button>
          )}

          {/* 清理按钮 */}
          <button
            type="button"
            onClick={() => {
              clearConsoleLogs();
              clearNetworkAnomalies();
            }}
            className="flex items-center gap-1 rounded border border-slate-700/60 bg-slate-800/80 px-2 py-1 text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
            title="清空当前所有异常记录"
            aria-label="清空当前所有异常记录"
          >
            <Trash2 className="w-3 h-3" />
            <span>清空</span>
          </button>
        </div>
      </div>

      {/* 展开的明细面板 */}
      {isExpanded && (
        <div className="flex flex-col h-44 overflow-hidden">
          {/* 子标签切换 */}
          <div className="flex items-center gap-2 px-3 pt-2 pb-1 border-b border-slate-800/50 bg-slate-950/40 text-[11px]">
            <button
              type="button"
              onClick={() => {
                setActiveTab('console');
              }}
              className={`flex items-center gap-1 px-2 py-0.5 rounded transition-colors ${
                activeTab === 'console'
                  ? 'bg-slate-800 text-indigo-400 font-medium'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Bug className="w-3 h-3" />
              <span>Console 报错 ({consoleErrors.length})</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('network');
              }}
              className={`flex items-center gap-1 px-2 py-0.5 rounded transition-colors ${
                activeTab === 'network'
                  ? 'bg-slate-800 text-indigo-400 font-medium'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Globe className="w-3 h-3" />
              <span>网络 404 / 异常 ({networkAnomalies.length})</span>
            </button>
          </div>

          {/* 异常流水日志 */}
          <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] space-y-1.5 bg-slate-950/80">
            {activeTab === 'console' && (
              consoleErrors.length === 0 ? (
                <div className="flex h-full items-center justify-center text-slate-500">
                  <CheckCircle2 className="w-4 h-4 mr-1.5 text-emerald-500/60" />
                  <span>控制台干净无报错，未检测到 TypeError 或白屏风险</span>
                </div>
              ) : (
                consoleErrors.map((err) => (
                  <div
                    key={err.id}
                    className="p-1.5 rounded border border-rose-900/40 bg-rose-950/20 text-rose-300"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-rose-400">[{err.level.toUpperCase()}] {err.message}</span>
                      <span className="text-[10px] text-slate-500">
                        {new Date(err.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    {err.stack && (
                      <pre className="mt-1 text-[10px] text-slate-400 whitespace-pre-wrap overflow-x-auto">
                        {err.stack}
                      </pre>
                    )}
                  </div>
                ))
              )
            )}

            {activeTab === 'network' && (
              networkAnomalies.length === 0 ? (
                <div className="flex h-full items-center justify-center text-slate-500">
                  <CheckCircle2 className="w-4 h-4 mr-1.5 text-emerald-500/60" />
                  <span>所有静态资产与 API 请求正常，零 404 / 500 异常</span>
                </div>
              ) : (
                networkAnomalies.map((net) => (
                  <div
                    key={net.id}
                    className="p-1.5 rounded border border-amber-900/40 bg-amber-950/20 text-amber-300 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-2">
                      <span className="px-1 py-0.2 rounded bg-amber-500/20 text-amber-400 font-bold">
                        {net.status} {net.statusText}
                      </span>
                      <span className="text-slate-300">{net.method}</span>
                      <span className="text-slate-400 truncate max-w-md">{net.url}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">
                      {new Date(net.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))
              )
            )}
          </div>
        </div>
      )}
    </section>
  );
};
