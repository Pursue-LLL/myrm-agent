import React, { useMemo } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Clock,
  X,
  Layers,
  Inbox,
} from 'lucide-react';
import { useExecutiveApprovalStore } from './useExecutiveApprovalStore';
import { computeApprovalStats } from './executiveApprovalEngine';
import { ExecutiveApprovalCard } from './ExecutiveApprovalCard';
import type { ApprovalRiskLevel, ApprovalStatus } from './executiveApprovalTypes';

export interface VisualGatekeepingDeckProps {
  readonly className?: string;
  readonly onClose?: () => void;
}

export const VisualGatekeepingDeck: React.FC<VisualGatekeepingDeckProps> = ({
  className = '',
  onClose,
}) => {
  const {
    requests,
    selectedRequestId,
    filterRiskLevel,
    filterStatus,
    selectRequest,
    setRiskFilter,
    setStatusFilter,
    toggleDeck,
  } = useExecutiveApprovalStore();

  const stats = useMemo(() => {
    return computeApprovalStats(requests);
  }, [requests]);

  const filteredRequests = useMemo(() => {
    return requests.filter((item) => {
      if (filterStatus !== 'all' && item.status !== filterStatus) {
        return false;
      }
      if (filterRiskLevel !== 'all' && item.riskLevel !== filterRiskLevel) {
        return false;
      }
      return true;
    });
  }, [requests, filterStatus, filterRiskLevel]);

  const activeRequest = useMemo(() => {
    if (selectedRequestId) {
      const found = requests.find((r) => {
        return r.id === selectedRequestId;
      });
      if (found) {
        return found;
      }
    }
    return filteredRequests[0] ?? null;
  }, [requests, selectedRequestId, filteredRequests]);

  const handleClose = () => {
    toggleDeck(false);
    if (onClose) {
      onClose();
    }
  };

  return (
    <div
      data-testid="visual-gatekeeping-deck"
      className={`rounded-2xl border border-slate-700/80 bg-slate-900/95 p-5 shadow-2xl backdrop-blur-md text-slate-100 ${className}`}
    >
      {/* 头部：标题与关闭按钮 */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">
              董事长把关审批与授权中枢
            </h3>
            <p className="text-[11px] text-slate-400">
              多智能体关键节点风控拦截 · 批准 / 驳回 / 现场就地修改
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={handleClose}
          aria-label="关闭审批中枢"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 统计指标胶囊 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 my-3.5">
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] text-amber-400">
            <Clock className="h-3.5 w-3.5" />
            <span>待我把关</span>
          </div>
          <p className="mt-1 text-lg font-bold text-amber-300">{stats.pendingCount}</p>
        </div>

        <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] text-rose-400">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>高危红线拦截</span>
          </div>
          <p className="mt-1 text-lg font-bold text-rose-300">{stats.highRiskCount}</p>
        </div>

        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] text-emerald-400">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>已通过放行</span>
          </div>
          <p className="mt-1 text-lg font-bold text-emerald-300">{stats.approvedCount}</p>
        </div>

        <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <Layers className="h-3.5 w-3.5" />
            <span>工单总池</span>
          </div>
          <p className="mt-1 text-lg font-bold text-slate-200">{stats.totalCount}</p>
        </div>
      </div>

      {/* 过滤标签栏 */}
      <div className="flex flex-wrap items-center gap-2 mb-3 text-xs">
        <span className="text-slate-400 text-[11px]">状态:</span>
        {(['all', 'pending', 'approved', 'rejected'] as const).map((status) => {
          const isSelected = filterStatus === status;
          const labelMap: Record<ApprovalStatus | 'all', string> = {
            all: '全部',
            pending: '仅待办',
            approved: '已批准',
            rejected: '已驳回',
            modified_approved: '现场修改',
          };
          return (
            <button
              key={status}
              type="button"
              onClick={() => {
                setStatusFilter(status);
              }}
              className={`rounded-lg px-2.5 py-1 transition-colors ${
                isSelected
                  ? 'bg-indigo-600 text-white font-medium shadow-xs'
                  : 'bg-slate-800 text-slate-400 hover:text-slate-200'
              }`}
            >
              {labelMap[status]}
            </button>
          );
        })}

        <span className="text-slate-400 text-[11px] ml-2">风险:</span>
        {(['all', 'high', 'critical'] as const).map((risk) => {
          const isSelected = filterRiskLevel === risk;
          const labelMap: Record<ApprovalRiskLevel | 'all', string> = {
            all: '全部风险',
            low: '低风险',
            medium: '中风险',
            high: '高风险',
            critical: '严重红线',
          };
          return (
            <button
              key={risk}
              type="button"
              onClick={() => {
                setRiskFilter(risk);
              }}
              className={`rounded-lg px-2 py-0.5 text-[11px] transition-colors ${
                isSelected
                  ? 'bg-indigo-600/80 text-white font-medium'
                  : 'bg-slate-800/80 text-slate-400 hover:text-slate-200'
              }`}
            >
              {labelMap[risk]}
            </button>
          );
        })}
      </div>

      {/* 核心工作区分栏/列表 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* 左侧列表 */}
        <div className="md:col-span-1 space-y-2 max-h-96 overflow-y-auto pr-1">
          {filteredRequests.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center border border-dashed border-slate-800 rounded-xl">
              <Inbox className="h-6 w-6 text-slate-500 mb-1" />
              <p className="text-xs text-slate-400">暂无匹配的待把关工单</p>
            </div>
          ) : (
            filteredRequests.map((req) => {
              const isSelected = activeRequest?.id === req.id;
              return (
                <button
                  key={req.id}
                  type="button"
                  onClick={() => {
                    selectRequest(req.id);
                  }}
                  className={`w-full text-left rounded-xl border p-2.5 transition-all ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-950/30'
                      : 'border-slate-800 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-center justify-between text-[11px] mb-1">
                    <span className="font-semibold text-slate-300 truncate max-w-[130px]">
                      {req.agentName}
                    </span>
                    <span
                      className={`text-[9px] font-medium px-1.5 py-0.2 rounded ${
                        req.riskLevel === 'critical'
                          ? 'bg-rose-500/20 text-rose-300'
                          : req.riskLevel === 'high'
                            ? 'bg-amber-500/20 text-amber-300'
                            : 'bg-blue-500/20 text-blue-300'
                      }`}
                    >
                      {req.riskLevel}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-slate-200 truncate">{req.actionTitle}</p>
                  <p className="text-[10px] text-slate-400 truncate mt-0.5">{req.targetChannel}</p>
                </button>
              );
            })
          )}
        </div>

        {/* 右侧选中的卡片详细操作区 */}
        <div className="md:col-span-2">
          {activeRequest ? (
            <ExecutiveApprovalCard request={activeRequest} />
          ) : (
            <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800 rounded-xl h-full">
              <ShieldCheck className="h-8 w-8 text-slate-600 mb-2" />
              <p className="text-xs text-slate-400">选择左侧任意工单进行现场把关</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
