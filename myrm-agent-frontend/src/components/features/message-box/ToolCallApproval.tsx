/**
 * 工具调用审批组件
 *
 * 1. 本文件的 INPUT/OUTPUT/POS 注释
 * 2. 所属文件夹的 _ARCH.md（如有）
 *
 * [INPUT]
 * - @/store/chat/types::ToolCallInfo (POS: 工具调用信息类型)
 * - @/lib/utils/classnameUtils::cn (POS: 类名合并工具)
 * - lucide-react: 图标组件
 *
 * [OUTPUT]
 * - ToolCallApproval: 工具调用审批组件
 *   - 显示待审批的工具调用列表
 *   - 每个工具调用显示：图标、名称、参数、状态
 *   - 提供批准/拒绝按钮
 *
 * [POS]
 * CLI Agent 工具调用审批组件。当 CLI Agent 执行敏感操作（如写文件、
 * 运行命令）时，显示权限请求弹窗，让用户批准或拒绝。支持三种权限模式：
 * Explore（只读）、Ask（每次询问）、Auto（自动批准）。在 MessageBox 中
 * 渲染，是 CLI 可视化工具的核心交互组件。
 */

'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, X, Loader2, Terminal, FileCode, Search, Globe } from 'lucide-react';
import { ToolCallInfo } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';
import { humanizeApprovalTitle } from '@/lib/humanize';
import { isSaveSkillApproval } from '@/lib/approval/saveSkillApproval';
import ApprovalScopeNoteLine from '@/components/approval/ApprovalScopeNoteLine';
import PtcHintBadges from '@/components/approval/PtcHintBadges';
import SaveSkillApprovalPreview from '@/components/approval/SaveSkillApprovalPreview';

interface ToolCallApprovalProps {
  toolCalls: ToolCallInfo[];
  chatId: string;
  onApprove: (callId: string) => Promise<void>;
  onReject: (callId: string) => Promise<void>;
}

/** 工具图标映射 */
const getToolIcon = (toolName: string) => {
  const name = toolName.toLowerCase();
  if (name.includes('bash') || name.includes('shell') || name.includes('terminal')) {
    return Terminal;
  }
  if (name.includes('file') || name.includes('write') || name.includes('read')) {
    return FileCode;
  }
  if (name.includes('search') || name.includes('grep')) {
    return Search;
  }
  if (name.includes('web') || name.includes('http')) {
    return Globe;
  }
  return Terminal;
};

/** 状态颜色映射 */
function getStatusBadge(status: ToolCallInfo['status'], label: string) {
  const baseClasses = 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium';
  switch (status) {
    case 'pending':
      return (
        <span className={cn(baseClasses, 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300')}>
          {label}
        </span>
      );
    case 'approved':
      return (
        <span className={cn(baseClasses, 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300')}>
          {label}
        </span>
      );
    case 'rejected':
      return (
        <span className={cn(baseClasses, 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300')}>{label}</span>
      );
    case 'completed':
      return (
        <span className={cn(baseClasses, 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300')}>
          {label}
        </span>
      );
  }
}

/** 单个工具调用项 */
const ToolCallItem: React.FC<{
  toolCall: ToolCallInfo;
  onApprove: () => Promise<void>;
  onReject: () => Promise<void>;
}> = ({ toolCall, onApprove, onReject }) => {
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null);
  const t = useTranslations('toolApproval');
  const tHumanize = useTranslations('humanize');
  const Icon = getToolIcon(toolCall.toolName);
  const displayTitle = humanizeApprovalTitle(toolCall.toolName, toolCall.arguments, tHumanize);
  const isSaveSkill = isSaveSkillApproval(toolCall.toolName, toolCall.arguments);
  const isPending = toolCall.status === 'pending' && toolCall.requiresApproval;

  const handleApprove = async () => {
    setLoading('approve');
    try {
      await onApprove();
    } finally {
      setLoading(null);
    }
  };

  const handleReject = async () => {
    setLoading('reject');
    try {
      await onReject();
    } finally {
      setLoading(null);
    }
  };

  return (
    <div
      className={cn(
        'rounded-lg border p-4 transition-all duration-200',
        isPending
          ? 'border-yellow-300 bg-yellow-50/50 dark:border-yellow-700 dark:bg-yellow-900/10'
          : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
      )}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">
          <div className="flex items-center gap-2 min-w-0">
            <Icon className="h-4 w-4 text-gray-500 dark:text-gray-400 shrink-0" />
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{displayTitle}</span>
          </div>

          {toolCall.ptcAnnotations ? <PtcHintBadges annotations={toolCall.ptcAnnotations} t={t} /> : null}
        </div>
        {getStatusBadge(toolCall.status, t(`toolCallStatus.${toolCall.status}`))}
      </div>

      <ApprovalScopeNoteLine
        toolName={toolCall.toolName}
        toolInput={toolCall.arguments}
        tHumanize={tHumanize}
        className="block mb-2"
      />

      {/* 参数显示 */}
      {typeof toolCall.arguments.reason === 'string' && toolCall.arguments.reason.trim() && (
        <div className="mb-2 text-xs text-foreground/90 rounded border border-border/60 bg-muted/30 px-2 py-1.5">
          <span className="font-medium text-muted-foreground">{t('executionIntent')}: </span>
          {String(toolCall.arguments.reason).trim()}
        </div>
      )}
      {Object.keys(toolCall.arguments).length > 0 && !isSaveSkill && (
        <div className="mb-3">
          <pre className="text-xs bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-x-auto max-h-32 text-gray-700 dark:text-gray-300">
            {JSON.stringify(
              Object.fromEntries(Object.entries(toolCall.arguments).filter(([key]) => key !== 'reason')),
              null,
              2,
            )}
          </pre>
        </div>
      )}
      {isSaveSkill ? (
        <div className="mb-3">
          <SaveSkillApprovalPreview
            toolInput={toolCall.arguments}
            showFullInstructionsLabel={t('saveSkill.showFullInstructions')}
            showLessLabel={t('saveSkill.showLess')}
            showAllLinesLabel={t('saveSkill.showAllLines')}
            footerText={t('saveSkill.footer')}
          />
        </div>
      ) : null}

      {/* 操作按钮 */}
      {isPending && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={handleApprove}
            disabled={loading !== null}
            className={cn(
              'flex-1 flex items-center justify-center gap-1 px-3 py-2 rounded-full text-sm font-medium transition-colors',
              'bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {loading === 'approve' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            {isSaveSkill ? t('saveSkill.approve') : t('approve')}
          </button>
          <button
            onClick={handleReject}
            disabled={loading !== null}
            className={cn(
              'flex-1 flex items-center justify-center gap-1 px-3 py-2 rounded-full text-sm font-medium transition-colors',
              'bg-red-600 hover:bg-red-700 text-white disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {loading === 'reject' ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
            {isSaveSkill ? t('saveSkill.deny') : t('reject')}
          </button>
        </div>
      )}
    </div>
  );
};

/** 工具调用批准组件 */
const ToolCallApproval: React.FC<ToolCallApprovalProps> = ({ toolCalls, onApprove, onReject }) => {
  const t = useTranslations('toolApproval');

  if (!toolCalls || toolCalls.length === 0) {
    return null;
  }

  const pendingCount = toolCalls.filter((tc) => tc.status === 'pending' && tc.requiresApproval).length;

  return (
    <div className="space-y-3 my-4">
      {pendingCount > 0 && (
        <div className="flex items-center gap-2 text-sm text-yellow-600 dark:text-yellow-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>{t('toolCallPendingBanner', { count: pendingCount })}</span>
        </div>
      )}
      <div className="grid gap-3">
        {toolCalls.map((toolCall) => (
          <ToolCallItem
            key={toolCall.callId}
            toolCall={toolCall}
            onApprove={() => onApprove(toolCall.callId)}
            onReject={() => onReject(toolCall.callId)}
          />
        ))}
      </div>
    </div>
  );
};

export default ToolCallApproval;
