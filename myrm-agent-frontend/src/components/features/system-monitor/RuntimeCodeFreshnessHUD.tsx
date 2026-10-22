/**
 * [INPUT]: Runtime code freshness report, module drift details, and inspection callbacks.
 * [OUTPUT]: High-performance dashboard HUD visualizing in-memory runtime code vs on-disk filesystem script freshness.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/RuntimeCodeFreshnessHUD.tsx
 */

import React, { useState } from 'react';
import {
  FreshnessStateType,
  RuntimeCodeFreshnessHUDProps,
} from './codeFreshnessTypes';

export const RuntimeCodeFreshnessHUD: React.FC<RuntimeCodeFreshnessHUDProps> = ({
  report,
  onRecheck,
  onInspectModule,
  isChecking = false,
}) => {
  const [filterState, setFilterState] = useState<FreshnessStateType | 'all'>('all');
  const [customPath, setCustomPath] = useState('');
  const [customModuleName, setCustomModuleName] = useState('');
  const [inspectingCustom, setInspectingCustom] = useState(false);

  const filteredDetails =
    filterState === 'all'
      ? report.details
      : report.details.filter((d) => d.state === filterState);

  const handleCustomInspect = async () => {
    if (!customPath.trim() || !onInspectModule) return;
    try {
      setInspectingCustom(true);
      await onInspectModule(
        customModuleName.trim() || 'custom_module',
        customPath.trim()
      );
    } finally {
      setInspectingCustom(false);
    }
  };

  const statusBadgeColor: Record<FreshnessStateType, string> = {
    fresh: 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60',
    stale: 'bg-rose-950/80 text-rose-300 border-rose-700/60',
    indeterminate: 'bg-amber-950/80 text-amber-300 border-amber-700/60',
  };

  const statusText: Record<FreshnessStateType, string> = {
    fresh: '✓ 全量代码最新 (Fresh)',
    stale: '⚠️ 存在旧代码静默执行 (Stale)',
    indeterminate: '❓ 部分模块不可判定 (Indeterminate)',
  };

  return (
    <div
      data-testid="runtime-code-freshness-hud"
      className="p-5 bg-neutral-900 border border-neutral-800 rounded-xl text-neutral-100 shadow-xl space-y-6"
    >
      {/* 顶部控制栏与整体体征胶囊 */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-neutral-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-cyan-400">⚡</span> 运行时代码新鲜度三态判定大盘
            </span>
            <span
              className={`px-2.5 py-0.5 text-xs font-semibold rounded-full border ${
                statusBadgeColor[report.overall_state]
              }`}
            >
              {statusText[report.overall_state]}
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            进程内存字节码 vs 磁盘源码 mtime 毫秒级比对 · 防热部署旧代码静默执行 · 显式不可判定归因
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs px-2.5 py-1 bg-neutral-800 rounded-lg text-neutral-300 border border-neutral-700 font-mono">
            PID: {report.pid}
          </span>
          {onRecheck && (
            <button
              type="button"
              data-testid="btn-recheck-freshness"
              onClick={onRecheck}
              disabled={isChecking}
              className="px-3 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition"
            >
              {isChecking ? '体检中...' : '重新体检'}
            </button>
          )}
        </div>
      </div>

      {/* 核心 KPI 指标卡片 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">已巡检入口模块</div>
          <div className="text-2xl font-bold text-white mt-1">
            {report.total_inspected_modules} 个
          </div>
        </div>

        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">最新匹配模块 (Fresh)</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">
            {report.fresh_modules_count} 个
          </div>
        </div>

        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">陈旧落后模块 (Stale)</div>
          <div
            className={`text-2xl font-bold mt-1 ${
              report.stale_modules_count > 0 ? 'text-rose-400' : 'text-neutral-400'
            }`}
          >
            {report.stale_modules_count} 个
          </div>
        </div>

        <div className="bg-neutral-800/70 p-4 rounded-xl border border-neutral-700/60">
          <div className="text-xs text-neutral-400">不可判定模块</div>
          <div className="text-2xl font-bold text-amber-400 mt-1">
            {report.indeterminate_count} 个
          </div>
        </div>
      </div>

      {/* 快捷单模块体检输入栏 */}
      {onInspectModule && (
        <div className="bg-neutral-800/40 p-4 rounded-xl border border-neutral-700/60 space-y-3">
          <h4 className="text-xs font-semibold text-neutral-300">
            🔍 单模块指定文件即时新鲜度抽检
          </h4>
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              data-testid="input-custom-module-name"
              placeholder="模块标识 (如 app.api.router)"
              value={customModuleName}
              onChange={(e) => setCustomModuleName(e.target.value)}
              className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 rounded-lg text-xs text-white placeholder-neutral-500 w-48"
            />
            <input
              type="text"
              data-testid="input-custom-module-path"
              placeholder="磁盘绝对路径 (如 /app/main.py)"
              value={customPath}
              onChange={(e) => setCustomPath(e.target.value)}
              className="px-3 py-1.5 bg-neutral-800 border border-neutral-700 rounded-lg text-xs text-white placeholder-neutral-500 flex-1 min-w-[200px]"
            />
            <button
              type="button"
              data-testid="btn-inspect-custom"
              onClick={handleCustomInspect}
              disabled={inspectingCustom || !customPath.trim()}
              className="px-3.5 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition disabled:opacity-50"
            >
              {inspectingCustom ? '核验中...' : '即时抽验'}
            </button>
          </div>
        </div>
      )}

      {/* 模块明细列表与筛选 */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
            📑 受控模块代码新鲜度体检明细 ({filteredDetails.length})
          </h4>
          <div className="flex bg-neutral-800 p-0.5 rounded-lg border border-neutral-700 text-xs">
            {(['all', 'fresh', 'stale', 'indeterminate'] as const).map((st) => (
              <button
                key={st}
                type="button"
                data-testid={`filter-${st}`}
                onClick={() => setFilterState(st)}
                className={`px-2.5 py-1 rounded-md transition ${
                  filterState === st
                    ? 'bg-neutral-700 text-white font-semibold'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {st.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-neutral-800/40 rounded-xl border border-neutral-700/60 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-neutral-300">
              <thead className="bg-neutral-800/80 text-neutral-400 border-b border-neutral-700/60">
                <tr>
                  <th className="py-2.5 px-3">模块标识</th>
                  <th className="py-2.5 px-3">文件路径</th>
                  <th className="py-2.5 px-3">状态</th>
                  <th className="py-2.5 px-3">时钟漂移</th>
                  <th className="py-2.5 px-3">不可判原因 / 修复引导</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {filteredDetails.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-neutral-500">
                      无匹配的模块记录
                    </td>
                  </tr>
                ) : (
                  filteredDetails.map((item) => (
                    <tr key={item.module_name} className="hover:bg-neutral-800/50 transition">
                      <td className="py-2.5 px-3 font-semibold text-white">
                        {item.module_name}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-neutral-400 truncate max-w-[200px]">
                        {item.file_path}
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border ${
                            statusBadgeColor[item.state]
                          }`}
                        >
                          {item.state.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-2.5 px-3">
                        {item.time_drift_seconds !== null && item.time_drift_seconds !== undefined ? (
                          <span
                            className={`font-mono font-medium ${
                              item.time_drift_seconds > 0 ? 'text-rose-400' : 'text-emerald-400'
                            }`}
                          >
                            {item.time_drift_seconds > 0 ? `+${item.time_drift_seconds}s (落后)` : `${item.time_drift_seconds}s`}
                          </span>
                        ) : (
                          <span className="text-neutral-500">-</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-neutral-400">
                        {item.reason !== 'none' && (
                          <span className="text-amber-400 mr-2 font-medium">
                            [{item.reason}]
                          </span>
                        )}
                        <span>{item.remediation_hint}</span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
