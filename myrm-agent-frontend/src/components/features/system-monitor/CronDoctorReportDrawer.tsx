/**
 * [INPUT]
 * - isOpen: boolean
 * - report: CronFleetDoctorReport | null
 * - onClose: () => void
 * - onQuickFix?: (job_id: string, category: string, remediation_param?: string) => Promise<QuickFixResponse | void>
 * - loadingFixJobId?: string | null
 *
 * [OUTPUT]
 * - CronDoctorReportDrawer: 定时任务舰队隐患自查与快速治愈抽屉组件
 *
 * [POS]
 * src/components/features/system-monitor/CronDoctorReportDrawer.tsx — 定时任务隐患详情与外科手术修复抽屉
 */

import React, { useState } from 'react';
import type { CronFleetDoctorReport, CronJobHealthIssue, QuickFixResponse } from './cronDoctorTypes';

export interface CronDoctorReportDrawerProps {
  isOpen: boolean;
  report: CronFleetDoctorReport | null;
  onClose: () => void;
  onQuickFix?: (job_id: string, category: string, remediation_param?: string) => Promise<QuickFixResponse | void>;
  loadingFixJobId?: string | null;
}

const CATEGORY_LABEL_MAP: Record<string, { label: string; desc: string }> = {
  EXECUTION_FAILED: { label: '执行崩溃', desc: '上次运行抛出未捕获异常或非零状态码退出' },
  DELIVERY_FAILED: { label: '交付失败', desc: '任务产物向目标信道投递失败' },
  DELIVERY_UNVERIFIED: { label: '回执未验真', desc: '投递完成但未收到 webhook 确认回执' },
  SCHEDULE_OVERDUE: { label: '调度逾期卡死', desc: '超过预定时间 10 分钟未被触发执行' },
  SCRIPT_NOT_FOUND: { label: '脚本文件缺失', desc: '配置的入口脚本在磁盘上未找到' },
  WORKDIR_NOT_FOUND: { label: '工作目录丢失', desc: '关联的沙箱执行目录不存在或损坏' },
};

export const CronDoctorReportDrawer: React.FC<CronDoctorReportDrawerProps> = ({
  isOpen,
  report,
  onClose,
  onQuickFix,
  loadingFixJobId = null,
}) => {
  const [fixedJobIds, setFixedJobIds] = useState<Record<string, string>>({});
  const [activeFixingId, setActiveFixingId] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFix = async (issue: CronJobHealthIssue) => {
    if (!onQuickFix) return;
    try {
      setActiveFixingId(issue.job_id);
      const res = await onQuickFix(issue.job_id, String(issue.category));
      if (res && typeof res === 'object' && 'message' in res) {
        setFixedJobIds((prev) => ({ ...prev, [issue.job_id]: res.message }));
      } else {
        setFixedJobIds((prev) => ({ ...prev, [issue.job_id]: '修复指令已成功下发并执行' }));
      }
    } catch {
      setFixedJobIds((prev) => ({ ...prev, [issue.job_id]: '快速修复失败，请查看系统日志' }));
    } finally {
      setActiveFixingId(null);
    }
  };

  const isFleetHealthy = report?.is_fleet_healthy ?? false;
  const issues = report?.issues ?? [];

  return (
    <div
      data-testid="cron-doctor-drawer-overlay"
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity"
    >
      <div
        data-testid="cron-doctor-drawer"
        className="w-full max-w-2xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl overflow-hidden"
      >
        {/* 抽屉头部 */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-sm">
              Dr
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-100">定时任务全景健康体检报告</h2>
              <p className="text-xs text-slate-400">Hermes Cron Doctor 6 大静默隐患主动防御巡检</p>
            </div>
          </div>
          <button
            onClick={onClose}
            data-testid="close-drawer-btn"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition"
            aria-label="关闭"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 抽屉内容区 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* 体检概要状态卡片 */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/60 flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="text-xs text-slate-400">巡检结果：</span>
                <span
                  data-testid="drawer-fleet-status-badge"
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    isFleetHealthy
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  }`}
                >
                  {isFleetHealthy ? '全部健康' : `发现 ${issues.length} 处隐患`}
                </span>
              </div>
              <p className="text-xs text-slate-400">
                受检任务：{report?.total_jobs ?? 0} 个 ｜ 正常运行：{report?.healthy_jobs_count ?? 0} 个 ｜ 巡检时间：{report?.inspected_at || '刚刚'}
              </p>
            </div>
          </div>

          {/* 若全健康：展示守卫清单 */}
          {isFleetHealthy && (
            <div
              data-testid="all-healthy-banner"
              className="p-6 rounded-xl bg-emerald-950/20 border border-emerald-800/40 text-center space-y-3"
            >
              <div className="w-12 h-12 mx-auto rounded-full bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-emerald-200">舰队防御门禁全部通过，零静默失效隐患</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                已验证无任何未捕获执行崩溃、交付信道通畅、回执均已完成验真、无调度逾期卡死、入口脚本完好且工作区目录均健康挂载。
              </p>
            </div>
          )}

          {/* 隐患列表 */}
          {!isFleetHealthy && issues.length > 0 && (
            <div className="space-y-3" data-testid="issues-list">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                待排查隐患清单 ({issues.length})
              </h4>

              {issues.map((issue) => {
                const categoryKey = String(issue.category).toUpperCase();
                const meta = CATEGORY_LABEL_MAP[categoryKey] || {
                  label: issue.category,
                  desc: '未知门禁异常',
                };
                const isCritical = issue.severity === 'critical';
                const isFixing =
                  loadingFixJobId === issue.job_id || activeFixingId === issue.job_id;
                const fixedMessage = fixedJobIds[issue.job_id];

                return (
                  <div
                    key={`${issue.job_id}-${issue.category}`}
                    data-testid="drawer-issue-item"
                    className="p-4 rounded-xl bg-slate-850/80 border border-slate-700/80 hover:border-slate-600 transition space-y-3"
                  >
                    {/* 隐患项头部 */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm font-semibold text-slate-100">{issue.job_name}</span>
                          <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded">
                            {issue.job_id}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span
                            className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${
                              isCritical
                                ? 'bg-rose-950/40 text-rose-300 border-rose-800/60'
                                : 'bg-amber-950/40 text-amber-300 border-amber-800/60'
                            }`}
                          >
                            {isCritical ? '致命隐患' : '警告风险'}
                          </span>
                          <span className="text-xs text-indigo-300 font-medium">{meta.label}</span>
                        </div>
                      </div>

                      {/* 外科手术修复按钮 */}
                      {onQuickFix && (
                        <button
                          onClick={() => handleFix(issue)}
                          disabled={isFixing || !!fixedMessage}
                          data-testid={`quick-fix-btn-${issue.job_id}`}
                          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition border flex items-center space-x-1.5 shrink-0 ${
                            fixedMessage
                              ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/50 cursor-default'
                              : 'bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500/50 disabled:opacity-50'
                          }`}
                        >
                          {isFixing ? (
                            <>
                              <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              <span>修复中...</span>
                            </>
                          ) : fixedMessage ? (
                            <>
                              <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                              </svg>
                              <span>已修复</span>
                            </>
                          ) : (
                            <>
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                              <span>外科手术快速修复</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>

                    {/* 隐患描述 */}
                    <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800 text-xs text-slate-300 space-y-1">
                      <div className="font-medium text-slate-200">故障诊断：{issue.message}</div>
                      <div className="text-slate-400 text-[11px]">{meta.desc}</div>
                    </div>

                    {/* 修复建议与修复结果 */}
                    <div className="text-xs text-emerald-400 bg-emerald-950/20 p-2.5 rounded-lg border border-emerald-900/40 flex items-start space-x-2">
                      <span className="font-semibold shrink-0">修复指引:</span>
                      <span className="text-emerald-300/90">{issue.suggested_fix}</span>
                    </div>

                    {fixedMessage && (
                      <div
                        data-testid={`fix-feedback-${issue.job_id}`}
                        className="text-xs text-indigo-300 bg-indigo-950/30 p-2 rounded-lg border border-indigo-800/40"
                      >
                        修复结果：{fixedMessage}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 抽屉底部 */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/90 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-lg transition"
          >
            完成并关闭
          </button>
        </div>
      </div>
    </div>
  );
};
