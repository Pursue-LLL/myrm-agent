/**
 * Cron Incident Drawer Component
 * 事故单待办诊断抽屉与一键 Ack 签收控制台
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范（dialog, output, label）；
 * 5. 行数严格受控在 400 行以内。
 */

import React from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  CheckCheck,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileX2,
  KeyRound,
  RefreshCw,
  Search,
  ShieldAlert,
  X,
  ZapOff,
} from 'lucide-react';
import { IncidentCategory, IncidentSeverity } from './cronIncidentTypes';
import { useCronIncidentStore } from './useCronIncidentStore';

const CATEGORY_TABS: Array<{ id: IncidentCategory | 'all'; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'silent_failure', label: '假成功静默失败' },
  { id: 'quota_exhausted', label: '配额耗尽 (429)' },
  { id: 'auth_expired', label: '密钥失效 (401)' },
  { id: 'timeout', label: '超时中断' },
  { id: 'runtime_crash', label: '异常崩溃' },
];

export const CronIncidentDrawer: React.FC = () => {
  const {
    isDrawerOpen,
    filterCategory,
    onlyUnacknowledged,
    searchQuery,
    setIsDrawerOpen,
    setFilterCategory,
    setOnlyUnacknowledged,
    setSearchQuery,
    acknowledgeIncident,
    acknowledgeAll,
    retryIncidentRun,
    getFilteredIncidents,
  } = useCronIncidentStore();

  if (!isDrawerOpen) {
    return null;
  }

  const incidents = getFilteredIncidents();
  const unackList = incidents.filter((i) => !i.acknowledged);

  const renderCategoryIcon = (category: IncidentCategory): React.ReactElement => {
    if (category === 'silent_failure') {
      return <FileX2 className="h-4 w-4 text-rose-400" />;
    }
    if (category === 'quota_exhausted') {
      return <ZapOff className="h-4 w-4 text-amber-400" />;
    }
    if (category === 'auth_expired') {
      return <KeyRound className="h-4 w-4 text-purple-400" />;
    }
    if (category === 'timeout') {
      return <Clock className="h-4 w-4 text-orange-400" />;
    }
    return <AlertOctagon className="h-4 w-4 text-red-400" />;
  };

  const renderSeverityBadge = (severity: IncidentSeverity): React.ReactElement => {
    if (severity === 'critical') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-rose-500/20 px-2 py-0.5 text-[10px] font-semibold text-rose-300">
          <ShieldAlert className="h-3 w-3" />
          <span>阻断故障</span>
        </span>
      );
    }
    if (severity === 'warning') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-300">
          <AlertTriangle className="h-3 w-3" />
          <span>告警</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded bg-blue-500/20 px-2 py-0.5 text-[10px] text-blue-300">
        <span>提示</span>
      </span>
    );
  };

  return (
    <dialog
      open
      data-testid="cron-incident-drawer-dialog"
      aria-label="定时任务事故待办中心抽屉"
      className="fixed inset-0 z-50 flex h-full w-full items-center justify-end bg-black/60 p-0 backdrop-blur-sm"
    >
      <div className="flex h-full w-full max-w-2xl flex-col border-l border-neutral-800 bg-neutral-950 p-6 text-neutral-100 shadow-2xl">
        {/* 抽屉头部 */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-rose-400" />
            <div>
              <h2 className="text-base font-semibold text-neutral-100">全局定时任务事故待办中心</h2>
              <p className="text-xs text-neutral-400">
                对标 Hermes 故障回执，识别假成功摸鱼欺诈与未产出交付物断言
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setIsDrawerOpen(false);
            }}
            data-testid="close-drawer-btn"
            className="rounded p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
            aria-label="关闭事故待办抽屉"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 顶部过滤控制台 */}
        <div className="my-3 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1">
              <label htmlFor="incident-search-input" className="sr-only">
                搜索受影响任务名称或报错特征
              </label>
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-neutral-500" />
              <input
                id="incident-search-input"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                }}
                placeholder="搜索受影响任务名称或报错特征..."
                className="w-full rounded-md border border-neutral-800 bg-neutral-900 py-1.5 pl-8 pr-3 text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none focus:ring-1 focus:ring-rose-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-neutral-400" htmlFor="toggle-unack-only">
                <input
                  id="toggle-unack-only"
                  type="checkbox"
                  checked={onlyUnacknowledged}
                  onChange={(e) => {
                    setOnlyUnacknowledged(e.target.checked);
                  }}
                  data-testid="toggle-unack-checkbox"
                  className="rounded border-neutral-700 bg-neutral-800 text-rose-600 focus:ring-0"
                />
                <span>仅看未签收</span>
              </label>

              {unackList.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    acknowledgeAll(unackList.map((i) => i.id));
                  }}
                  data-testid="ack-all-btn"
                  className="flex items-center gap-1 rounded bg-neutral-800 px-2.5 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-700"
                >
                  <CheckCheck className="h-3.5 w-3.5 text-emerald-400" />
                  <span>全部签收 ({unackList.length})</span>
                </button>
              )}
            </div>
          </div>

          {/* 分类筛选标签 */}
          <div className="flex flex-wrap gap-1.5 border-b border-neutral-800/80 pb-2">
            {CATEGORY_TABS.map((tab) => {
              const isActive = filterCategory === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => {
                    setFilterCategory(tab.id);
                  }}
                  data-testid={`category-tab-${tab.id}`}
                  className={`rounded-md px-2.5 py-1 text-xs transition-colors ${
                    isActive
                      ? 'bg-rose-950/60 font-medium text-rose-300 ring-1 ring-rose-500/50'
                      : 'bg-neutral-900 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-300'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 事故列表区域 */}
        <div className="flex-1 overflow-y-auto pr-1">
          {incidents.length === 0 ? (
            <output
              aria-live="polite"
              data-testid="empty-incident-notice"
              className="flex h-64 flex-col items-center justify-center gap-2 text-neutral-500"
            >
              <CheckCircle2 className="h-8 w-8 text-neutral-700" />
              <span className="text-xs">未匹配到任何定时任务事故记录</span>
            </output>
          ) : (
            <div className="flex flex-col gap-3">
              {incidents.map((incident) => {
                const isSilent = incident.category === 'silent_failure';
                return (
                  <section
                    key={incident.id}
                    data-testid={`incident-card-${incident.id}`}
                    aria-label={`事故单: ${incident.jobName}`}
                    className={`flex flex-col rounded-lg border p-3.5 text-xs transition-colors ${
                      incident.acknowledged
                        ? 'border-neutral-800/60 bg-neutral-900/30 opacity-60'
                        : isSilent
                        ? 'border-rose-500/40 bg-rose-950/20'
                        : 'border-neutral-800 bg-neutral-900/60'
                    }`}
                  >
                    {/* 事故卡片首行 */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {renderCategoryIcon(incident.category)}
                        <span className="font-semibold text-neutral-200">{incident.jobName}</span>
                        {renderSeverityBadge(incident.severity)}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-neutral-500">
                        <span>{new Date(incident.occurredAt).toLocaleTimeString()}</span>
                        {incident.acknowledged ? (
                          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-emerald-400">已签收</span>
                        ) : (
                          <span className="rounded bg-rose-950/80 px-1.5 py-0.5 text-rose-400">待办未签收</span>
                        )}
                      </div>
                    </div>

                    {/* 概要说明 */}
                    <div className="mt-2 text-neutral-300 font-medium">
                      {incident.summary}
                    </div>

                    {/* Exit Code 与假成功特别警示 */}
                    <div className="mt-1.5 flex items-center gap-2 font-mono text-[11px]">
                      <span className="text-neutral-500">Exit Code:</span>
                      <span
                        className={`font-bold ${
                          incident.exitCode === 0 ? 'text-rose-400 underline decoration-rose-500' : 'text-neutral-300'
                        }`}
                      >
                        {incident.exitCode}
                      </span>
                      {isSilent && (
                        <span className="rounded bg-rose-500/20 px-1.5 text-[10px] text-rose-300">
                          假成功警示: 进程无报错退出，物理产物为空
                        </span>
                      )}
                    </div>

                    {/* 失败断言详情 */}
                    <div className="mt-2 rounded bg-neutral-950/70 p-2 text-neutral-400">
                      <div className="text-[11px] font-medium text-neutral-400 mb-1">物理验收断言失败证据:</div>
                      <p className="font-mono text-[11px] text-rose-300/90 whitespace-pre-wrap">
                        {incident.failureReason}
                      </p>
                      {incident.verificationDetails?.missingArtifacts &&
                        incident.verificationDetails.missingArtifacts.length > 0 && (
                          <div className="mt-1 flex items-center gap-1 text-[11px] text-neutral-400">
                            <span>缺失交付物:</span>
                            {incident.verificationDetails.missingArtifacts.map((name) => (
                              <span key={name} className="rounded bg-neutral-800 px-1 font-mono text-neutral-300">
                                {name}
                              </span>
                            ))}
                          </div>
                        )}
                    </div>

                    {/* 底部操作行 */}
                    <div className="mt-3 flex items-center justify-between border-t border-neutral-800/80 pt-2.5">
                      <div className="flex items-center gap-2 text-[11px] text-neutral-500">
                        <span>Run: #{incident.runId}</span>
                        {incident.retryCount > 0 && <span>重试次数: {incident.retryCount}</span>}
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            retryIncidentRun(incident.id);
                          }}
                          data-testid={`retry-btn-${incident.id}`}
                          className="flex items-center gap-1 rounded border border-neutral-800 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
                        >
                          <RefreshCw className="h-3 w-3" />
                          <span>一键重跑</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            // 模拟深链跳转至任务执行详情
                            window.dispatchEvent(
                              new CustomEvent('myrm:jump-cron-history', {
                                detail: { jobId: incident.jobId, runId: incident.runId },
                              })
                            );
                          }}
                          data-testid={`jump-history-btn-${incident.id}`}
                          className="flex items-center gap-1 rounded border border-neutral-800 px-2 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
                          title="跳转至历史日志排查"
                        >
                          <ExternalLink className="h-3 w-3" />
                          <span>历史诊断</span>
                        </button>

                        {!incident.acknowledged && (
                          <button
                            type="button"
                            onClick={() => {
                              acknowledgeIncident(incident.id);
                            }}
                            data-testid={`ack-btn-${incident.id}`}
                            className="flex items-center gap-1 rounded bg-rose-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-rose-500"
                          >
                            <CheckCheck className="h-3.5 w-3.5" />
                            <span>确认签收 (Ack)</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </dialog>
  );
};
