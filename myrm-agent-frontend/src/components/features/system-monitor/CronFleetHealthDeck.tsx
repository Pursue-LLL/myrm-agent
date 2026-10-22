/**
 * [INPUT]
 * - CronFleetDoctorReport 定时舰队体检报告数据
 * - onScan: 重新发起全景健康巡检回调
 * - onOpenReport: 打开体检报告抽屉回调
 *
 * [OUTPUT]
 * - CronFleetHealthDeck: 定时任务舰队健康体态顶栏卡片组件
 *
 * [POS]
 * src/components/features/system-monitor/CronFleetHealthDeck.tsx — 定时任务舰队全景体检体态看板
 */

import React from 'react';
import type { CronFleetDoctorReport } from './cronDoctorTypes';

export interface CronFleetHealthDeckProps {
  report: CronFleetDoctorReport | null;
  loading?: boolean;
  onScan?: () => void;
  onOpenReport?: () => void;
  className?: string;
}

export const CronFleetHealthDeck: React.FC<CronFleetHealthDeckProps> = ({
  report,
  loading = false,
  onScan,
  onOpenReport,
  className = '',
}) => {
  if (!report) {
    return (
      <div
        data-testid="cron-fleet-health-loading"
        className={`p-4 bg-slate-900 border border-slate-800 rounded-xl flex items-center justify-between text-slate-400 ${className}`}
      >
        <div className="flex items-center space-x-3">
          <div className="w-4 h-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <span className="text-sm">正在加载定时任务舰队体检数据...</span>
        </div>
        {onScan && (
          <button
            onClick={onScan}
            disabled={loading}
            data-testid="scan-btn-initial"
            className="px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-800 hover:bg-slate-700 rounded-lg transition"
          >
            发起体检
          </button>
        )}
      </div>
    );
  }

  const { total_jobs, healthy_jobs_count, issues_count, is_fleet_healthy, issues, inspected_at } = report;

  const criticalCount = issues.filter((i) => i.severity === 'critical').length;
  const warningCount = issues.filter((i) => i.severity === 'warning').length;

  return (
    <div
      data-testid="cron-fleet-health-deck"
      className={`p-4 rounded-xl border transition-all ${
        is_fleet_healthy
          ? 'bg-slate-900/90 border-emerald-500/30 shadow-sm'
          : 'bg-slate-900/90 border-amber-500/40 shadow-md shadow-amber-950/20'
      } ${className}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        {/* 左侧：健康状态徽章与主文案 */}
        <div className="flex items-start sm:items-center space-x-3.5">
          <div
            data-testid="fleet-status-indicator"
            className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
              is_fleet_healthy
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse'
            }`}
          >
            {is_fleet_healthy ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            )}
          </div>

          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-semibold text-slate-100">定时任务舰队全景健康体检 (Hermes Cron Doctor)</h3>
              <span
                data-testid="fleet-status-badge"
                className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                  is_fleet_healthy
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                }`}
              >
                {is_fleet_healthy ? '健康良好 · 零故障隐患' : `存在 ${issues_count} 处静默隐患待处理`}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {is_fleet_healthy
                ? `活跃舰队 ${total_jobs} 个自动化定时任务全部健康，最近体检已通过 6 大防御门禁`
                : `侦测到 ${criticalCount > 0 ? `${criticalCount} 项致命异常、` : ''}${warningCount} 项未决隐患，可能导致静默漏发或脚本失效`}
            </p>
          </div>
        </div>

        {/* 右侧：统计数据与操作按钮 */}
        <div className="flex items-center space-x-3 self-end sm:self-center">
          <div className="hidden md:flex items-center space-x-4 px-3 py-1.5 bg-slate-800/60 rounded-lg text-xs text-slate-300 border border-slate-700/50">
            <div>
              <span className="text-slate-400">受检任务: </span>
              <span className="font-semibold text-slate-200">{total_jobs}</span>
            </div>
            <div className="w-px h-3 bg-slate-700" />
            <div>
              <span className="text-slate-400">健康: </span>
              <span className="font-semibold text-emerald-400">{healthy_jobs_count}</span>
            </div>
            <div className="w-px h-3 bg-slate-700" />
            <div>
              <span className="text-slate-400">隐患: </span>
              <span className={`font-semibold ${issues_count > 0 ? 'text-amber-400' : 'text-slate-200'}`}>
                {issues_count}
              </span>
            </div>
          </div>

          {onScan && (
            <button
              onClick={onScan}
              disabled={loading}
              data-testid="scan-btn"
              className="px-3 py-1.5 text-xs font-medium text-slate-200 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 rounded-lg border border-slate-700 transition flex items-center space-x-1.5"
            >
              {loading && <span className="w-3 h-3 rounded-full border-2 border-indigo-400 border-t-transparent animate-spin" />}
              <span>{loading ? '体检中...' : '重新体检'}</span>
            </button>
          )}

          {onOpenReport && (
            <button
              onClick={onOpenReport}
              data-testid="inspect-btn"
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition border flex items-center space-x-1 ${
                issues_count > 0
                  ? 'bg-amber-600 hover:bg-amber-500 text-white border-amber-500/50 shadow-sm'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border-slate-700'
              }`}
            >
              <span>{issues_count > 0 ? '排查隐患并修复' : '查看体检报告'}</span>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* 底部细化隐患预览条（仅在有隐患时显示） */}
      {issues_count > 0 && (
        <div
          data-testid="issues-summary-strip"
          className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between text-[11px] text-slate-400 gap-2"
        >
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-slate-400">已侦测门禁：</span>
            {issues.slice(0, 3).map((issue) => (
              <span
                key={`${issue.job_id}-${issue.category}`}
                className={`px-2 py-0.5 rounded border ${
                  issue.severity === 'critical'
                    ? 'bg-rose-950/40 text-rose-300 border-rose-800/60'
                    : 'bg-amber-950/40 text-amber-300 border-amber-800/60'
                }`}
              >
                {issue.job_name} ({issue.category})
              </span>
            ))}
            {issues.length > 3 && (
              <span className="text-slate-400">等共 {issues.length} 项</span>
            )}
          </div>
          <span className="text-slate-400">巡检时间: {inspected_at || '刚刚'}</span>
        </div>
      )}
    </div>
  );
};
