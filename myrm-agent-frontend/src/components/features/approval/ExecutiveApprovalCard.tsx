import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Edit3,
  Send,
  AlertTriangle,
  FileText,
  UserCheck,
} from 'lucide-react';
import { useExecutiveApprovalStore } from './useExecutiveApprovalStore';
import type { ApprovalRequest, ApprovalRiskLevel } from './executiveApprovalTypes';

export interface ExecutiveApprovalCardProps {
  readonly request: ApprovalRequest;
  readonly className?: string;
}

function getRiskBadgeStyle(level: ApprovalRiskLevel): {
  bg: string;
  text: string;
  border: string;
  label: string;
} {
  if (level === 'critical') {
    return {
      bg: 'bg-rose-500/15',
      text: 'text-rose-400',
      border: 'border-rose-500/30',
      label: '最高风控红线',
    };
  }
  if (level === 'high') {
    return {
      bg: 'bg-amber-500/15',
      text: 'text-amber-400',
      border: 'border-amber-500/30',
      label: '高危操作把关',
    };
  }
  if (level === 'medium') {
    return {
      bg: 'bg-yellow-500/15',
      text: 'text-yellow-400',
      border: 'border-yellow-500/30',
      label: '中等风险注意',
    };
  }
  return {
    bg: 'bg-blue-500/15',
    text: 'text-blue-400',
    border: 'border-blue-500/30',
    label: '常规沙箱协同',
  };
}

export const ExecutiveApprovalCard: React.FC<ExecutiveApprovalCardProps> = ({
  request,
  className = '',
}) => {
  const { approveRequest, rejectRequest, modifyAndApproveRequest } =
    useExecutiveApprovalStore();

  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState(
    request.modifiedContent ?? request.proposedContent
  );
  const [isRejecting, setIsRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const riskBadge = getRiskBadgeStyle(request.riskLevel);
  const isPending = request.status === 'pending';

  const handleApprove = () => {
    approveRequest(request.id);
  };

  const handleRejectSubmit = () => {
    if (!rejectReason.trim()) {
      return;
    }
    rejectRequest(request.id, rejectReason.trim());
    setIsRejecting(false);
  };

  const handleModifyAndApprove = () => {
    modifyAndApproveRequest(request.id, editedContent);
    setIsEditing(false);
  };

  return (
    <div
      data-testid={`approval-card-${request.id}`}
      className={`rounded-2xl border border-slate-700/80 bg-slate-900/90 p-5 shadow-xl backdrop-blur-md text-slate-100 ${className}`}
    >
      {/* 头部：智能体身份与风险分级徽章 */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
            <UserCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-200">
                {request.agentName}
              </span>
              <span className="text-[10px] text-slate-400">发起审批申请</span>
            </div>
            <p className="text-[10px] text-slate-400">目标渠道: {request.targetChannel}</p>
          </div>
        </div>

        <div
          className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${riskBadge.bg} ${riskBadge.text} ${riskBadge.border}`}
        >
          <ShieldAlert className="h-3.5 w-3.5" />
          <span>{riskBadge.label}</span>
        </div>
      </div>

      {/* 动作标题与执行摘要 */}
      <div className="py-3">
        <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
          <FileText className="h-4 w-4 text-indigo-400 shrink-0" />
          {request.actionTitle}
        </h4>
        <p className="mt-1 text-xs text-slate-300 leading-relaxed">{request.summary}</p>
      </div>

      {/* 拟执行内容/就地现场修改编辑区 */}
      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5 my-2">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            拟提交执行指令/文案
          </span>
          {isPending && !isEditing && (
            <button
              type="button"
              onClick={() => {
                setIsEditing(true);
              }}
              className="text-[11px] text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-1"
            >
              <Edit3 className="h-3 w-3" />
              就地修改
            </button>
          )}
        </div>

        {isEditing ? (
          <div className="space-y-2">
            <textarea
              value={editedContent}
              onChange={(e) => {
                setEditedContent(e.target.value);
              }}
              aria-label="编辑拟执行内容"
              className="w-full h-24 rounded-lg border border-slate-700 bg-slate-900 p-2.5 text-xs text-slate-100 font-mono focus:border-indigo-500 focus:outline-hidden"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                }}
                className="rounded-lg px-2.5 py-1 text-xs text-slate-400 hover:bg-slate-800"
              >
                取消修改
              </button>
              <button
                type="button"
                onClick={handleModifyAndApprove}
                className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
              >
                <Send className="h-3 w-3" />
                保存并批准
              </button>
            </div>
          </div>
        ) : (
          <pre className="text-xs text-slate-200 font-mono whitespace-pre-wrap break-all leading-relaxed bg-slate-900/50 p-2 rounded">
            {request.modifiedContent ?? request.proposedContent}
          </pre>
        )}
      </div>

      {/* 风险判定理由 */}
      <div className="text-[10px] text-slate-400 flex items-center gap-1.5 px-1 py-1">
        <span className="font-medium text-slate-400">风控审计依据:</span>
        <span>{request.riskReason}</span>
      </div>

      {/* 状态徽章或三态决策按钮栏 */}
      {!isPending ? (
        <div className="mt-3 pt-3 border-t border-slate-800 flex items-center justify-between text-xs">
          <div className="flex items-center gap-1.5">
            {request.status === 'approved' && (
              <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                <CheckCircle2 className="h-4 w-4" />
                董事长已批准执行
              </span>
            )}
            {request.status === 'modified_approved' && (
              <span className="inline-flex items-center gap-1 text-cyan-400 font-medium">
                <CheckCircle2 className="h-4 w-4" />
                董事长现场修改后批准
              </span>
            )}
            {request.status === 'rejected' && (
              <span className="inline-flex items-center gap-1 text-rose-400 font-medium">
                <XCircle className="h-4 w-4" />
                董事长已驳回重做
              </span>
            )}
          </div>
          {request.feedbackComment && (
            <span className="text-[11px] text-slate-400 truncate max-w-[200px]">
              批注: {request.feedbackComment}
            </span>
          )}
        </div>
      ) : (
        <div className="mt-3 pt-3 border-t border-slate-800 space-y-2">
          {isRejecting ? (
            <div className="space-y-2">
              <input
                type="text"
                placeholder="请输入驳回修改意见（如：修改文案语调、核减算力配额）"
                value={rejectReason}
                onChange={(e) => {
                  setRejectReason(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-rose-500 focus:outline-hidden"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsRejecting(false);
                  }}
                  className="rounded-lg px-2.5 py-1 text-xs text-slate-400 hover:bg-slate-800"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleRejectSubmit}
                  className="rounded-lg bg-rose-600 px-3 py-1 text-xs font-medium text-white hover:bg-rose-500"
                >
                  确认驳回
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => {
                  setIsRejecting(true);
                }}
                className="flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/20 transition-colors"
              >
                <XCircle className="h-3.5 w-3.5" />
                驳回重做
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsEditing(true);
                }}
                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors"
              >
                <Edit3 className="h-3.5 w-3.5" />
                现场修改
              </button>
              <button
                type="button"
                onClick={handleApprove}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-emerald-500 transition-colors"
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                一键批准执行
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
