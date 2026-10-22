'use client';

import React, { useEffect, useRef } from 'react';
import {
  Search,
  X,
  Pin,
  PinOff,
  Stethoscope,
  Wrench,
  Download,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  Layers,
  Cpu,
  Clock,
  Sparkles,
  Command,
} from 'lucide-react';
import { useCommandCenterHudStore } from './useCommandCenterHudStore';
import {
  filterWorkstreams,
  formatSpendTokens,
  formatSpendUsd,
} from './commandCenterEngine';
import { TimeRangeKey } from './commandCenterTypes';

export const CommandCenterHudModal: React.FC = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    isOpen,
    searchQuery,
    selectedTimeRange,
    gatewayHealth,
    diagnosticChecks,
    isRunningDoctor,
    pinnedWorkstreams,
    spendSummaries,
    lastBackupPayload,
    closeHud,
    toggleHud,
    setSearchQuery,
    setSelectedTimeRange,
    togglePinWorkstream,
    runDoctor,
    remediateIssue,
    backupConfig,
  } = useCommandCenterHudStore();

  // 绑定 Cmd+. / Ctrl+. 全局快捷键与 Escape 键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '.') {
        e.preventDefault();
        toggleHud();
      } else if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        closeHud();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, toggleHud, closeHud]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const currentSpend = spendSummaries[selectedTimeRange];
  const filteredWorkstreams = filterWorkstreams(pinnedWorkstreams, searchQuery);

  const renderStatusBadge = (status: 'pass' | 'warning' | 'error') => {
    if (status === 'pass') {
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" aria-hidden="true" />;
    }
    if (status === 'warning') {
      return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" aria-hidden="true" />;
    }
    return <XCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" aria-hidden="true" />;
  };

  return (
    <dialog
      open
      aria-label="全局 Command Center HUD 运维大厅"
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full max-w-none max-h-none m-0 p-4 border-0 bg-slate-950/80 backdrop-blur-xl animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-5xl rounded-3xl bg-slate-900/95 border border-slate-800 shadow-2xl flex flex-col overflow-hidden max-h-[90vh]">
        {/* 顶部搜索条与快捷键徽章 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900/80">
          <div className="flex items-center space-x-3 flex-1 mr-4">
            <Search className="w-5 h-5 text-slate-400 shrink-0" aria-hidden="true" />
            <input
              ref={inputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); }}
              placeholder="穿透检索所有历史会话、工作流、生成工件或系统命令..."
              aria-label="检索工作流与系统命令"
              className="w-full bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none"
            />
          </div>

          <div className="flex items-center space-x-2 shrink-0">
            <div className="hidden sm:flex items-center space-x-1 px-2 py-1 rounded-md bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-400">
              <Command className="w-3 h-3" aria-hidden="true" />
              <span>+ . 唤出</span>
            </div>

            <button
              type="button"
              onClick={closeHud}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              title="关闭 HUD (Esc)"
            >
              <X className="w-5 h-5" aria-hidden="true" />
            </button>
          </div>
        </div>

        {/* 主内容双栏分屏 */}
        <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-800 p-6 gap-6 lg:gap-0">
          {/* 左侧：7/30/90 天算力用量雷达 (占 6 列) */}
          <div className="lg:col-span-6 lg:pr-6 flex flex-col justify-between space-y-5">
            <div>
              <div className="flex items-center justify-between mb-3.5">
                <div className="flex items-center space-x-2">
                  <Activity className="w-4 h-4 text-sky-400" aria-hidden="true" />
                  <h4 className="text-xs font-bold text-slate-200">
                    算力消耗与热度大盘
                  </h4>
                </div>

                <div className="flex items-center space-x-1 bg-slate-800/80 p-0.5 rounded-lg border border-slate-700/60 text-xs">
                  {(['7d', '30d', '90d'] as TimeRangeKey[]).map((period) => (
                    <button
                      key={period}
                      type="button"
                      onClick={() => { setSelectedTimeRange(period); }}
                      className={`px-2 py-0.5 rounded-md font-medium text-[11px] transition-all ${
                        selectedTimeRange === period
                          ? 'bg-sky-500 text-white font-semibold shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {period.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {/* 核心指标卡片 */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="p-3 rounded-xl bg-slate-800/50 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 flex items-center space-x-1">
                    <Cpu className="w-3 h-3 text-sky-400" aria-hidden="true" />
                    <span>周期内总 Token</span>
                  </span>
                  <div className="text-lg font-bold font-mono text-slate-100 mt-1">
                    {formatSpendTokens(currentSpend.totalTokens)}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-800/50 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 flex items-center space-x-1">
                    <Sparkles className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                    <span>折算总算力成本</span>
                  </span>
                  <div className="text-lg font-bold font-mono text-emerald-400 mt-1">
                    {formatSpendUsd(currentSpend.estimatedCostUsd)}
                  </div>
                </div>
              </div>

              {/* Top 模型消耗占比 */}
              <div className="mb-4">
                <span className="text-[11px] font-semibold text-slate-400 mb-2 block">
                  高频模型负载分布:
                </span>
                <div className="space-y-2">
                  {currentSpend.topModels.map((m) => (
                    <div key={m.modelId} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-300 truncate">{m.name}</span>
                        <span className="text-slate-400 font-mono text-[11px]">
                          {formatSpendTokens(m.tokens)} ({m.percentage}%)
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          style={{ width: `${m.percentage}%` }}
                          className="h-full bg-sky-500 rounded-full"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Top 常用 Skills 列表 */}
              <div>
                <span className="text-[11px] font-semibold text-slate-400 mb-2 block">
                  常用技能工具热度榜:
                </span>
                <div className="space-y-1.5">
                  {currentSpend.topSkills.map((s, idx) => (
                    <div
                      key={s.skillId}
                      className="flex items-center justify-between p-2 rounded-lg bg-slate-800/30 border border-slate-800 text-xs"
                    >
                      <div className="flex items-center space-x-2 truncate">
                        <span className="w-4 text-center font-mono text-[10px] text-slate-500">
                          #{idx + 1}
                        </span>
                        <span className="text-slate-200 truncate">{s.name}</span>
                      </div>
                      <span className="text-[10px] font-mono text-sky-400 bg-sky-950/60 border border-sky-800/40 px-1.5 py-0.5 rounded">
                        {s.invocationCount} 次调用
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 右侧：一键健康体检、安全审计与配置备份 (占 6 列) */}
          <div className="lg:col-span-6 lg:pl-6 flex flex-col justify-between space-y-4">
            <div>
              <div className="flex items-center justify-between mb-3.5">
                <div className="flex items-center space-x-2">
                  <Stethoscope className="w-4 h-4 text-emerald-400" aria-hidden="true" />
                  <h4 className="text-xs font-bold text-slate-200">
                    系统全面体检与就地自愈
                  </h4>
                </div>

                <button
                  type="button"
                  onClick={runDoctor}
                  disabled={isRunningDoctor}
                  className="flex items-center space-x-1.5 px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold shadow-md transition-all active:scale-[0.98]"
                >
                  <Stethoscope className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>{isRunningDoctor ? '诊断体检中...' : '开始体检 (Doctor)'}</span>
                </button>
              </div>

              {/* 诊断检测条目 */}
              <div className="space-y-2 mb-4">
                {diagnosticChecks.map((chk) => (
                  <div
                    key={chk.id}
                    className="p-2.5 rounded-xl bg-slate-800/40 border border-slate-800 flex items-start justify-between space-x-3"
                  >
                    <div className="flex items-start space-x-2.5 min-w-0">
                      <div className="mt-0.5">{renderStatusBadge(chk.status)}</div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-slate-200 truncate">
                          {chk.name}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                          {chk.detail}
                        </p>
                      </div>
                    </div>

                    {chk.remediable && chk.status !== 'pass' && (
                      <button
                        type="button"
                        onClick={() => { remediateIssue(chk.id); }}
                        className="flex items-center space-x-1 px-2 py-1 rounded-md bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-[10px] font-semibold shrink-0 transition-colors"
                        title="执行就地自愈修复"
                      >
                        <Wrench className="w-3 h-3" aria-hidden="true" />
                        <span>自愈修复</span>
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {/* 导出配置与记忆备份 */}
              <div className="p-3 rounded-2xl bg-slate-800/30 border border-slate-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-200 flex items-center space-x-1.5">
                    <Download className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
                    <span>全局配置与记忆快照备份</span>
                  </span>
                  <button
                    type="button"
                    onClick={backupConfig}
                    className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
                  >
                    <span>导出快照</span>
                  </button>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  单键打包当前系统设置、工作流索引及系统体检档案，提供可迁移快照。
                </p>
                {lastBackupPayload && (
                  <div className="mt-2 p-2 rounded-lg bg-slate-950 font-mono text-[10px] text-emerald-400 truncate border border-slate-800">
                    快照生成成功: {lastBackupPayload.length} 字节已装箱就绪
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 底部：工作流穿透列表 */}
        <div className="border-t border-slate-800 bg-slate-900/90 px-6 py-3">
          <div className="flex items-center justify-between mb-2 text-xs font-semibold text-slate-400">
            <span>穿透工作流与最近会话 ({filteredWorkstreams.length})</span>
            <span className="text-[10px] text-slate-500">点击置顶或切换</span>
          </div>

          <div className="flex items-center space-x-2 overflow-x-auto pb-1 scrollbar-none">
            {filteredWorkstreams.map((ws) => (
              <div
                key={ws.id}
                className={`flex items-center space-x-2 px-3 py-1.5 rounded-xl border text-xs whitespace-nowrap transition-colors ${
                  ws.isPinned
                    ? 'bg-sky-500/10 text-sky-300 border-sky-500/30'
                    : 'bg-slate-800/60 text-slate-300 border-slate-700/60 hover:bg-slate-800'
                }`}
              >
                <Layers className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                <span className="font-medium truncate max-w-[200px]">{ws.title}</span>
                <span className="text-[10px] text-slate-500 flex items-center space-x-0.5">
                  <Clock className="w-2.5 h-2.5" aria-hidden="true" />
                  <span>{ws.lastActive}</span>
                </span>
                <button
                  type="button"
                  onClick={() => { togglePinWorkstream(ws.id); }}
                  className="p-0.5 text-slate-400 hover:text-slate-200"
                  title={ws.isPinned ? '取消置顶' : '置顶此项'}
                >
                  {ws.isPinned ? (
                    <Pin className="w-3 h-3 text-sky-400 fill-current" aria-hidden="true" />
                  ) : (
                    <PinOff className="w-3 h-3" aria-hidden="true" />
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </dialog>
  );
};
