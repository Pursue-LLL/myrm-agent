'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: toolApproval 文案)
 * - @/store/chat/types::ToolApprovalRequest (POS: 决定哪些按钮出现)
 *
 * [OUTPUT]
 * - ApprovalActions: 审批卡的操作按钮行（批准 / 编辑 / 拒绝 / 总是允许 / 允许该域名；被智能审核拦下时只有「仍然批准一次」和拒绝）
 *
 * [POS]
 * 只决定按钮的出现与禁用，点击后做什么由审批卡通过回调决定。
 */

import { CheckCircle2, Globe, MessageSquareX, Pencil, ShieldAlert } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Button } from '@/components/primitives/button';
import type { ToolApprovalRequest } from '@/store/chat/types';

interface ApprovalActionsProps {
  request: Pick<ToolApprovalRequest, 'smartDenied' | 'hideAllowAlways' | 'domainApproval' | 'domains'>;
  isLoading: boolean;
  isExpired: boolean;
  isAutoApproved: boolean;
  isSaveSkill: boolean;
  onApprove: () => void;
  onEdit: () => void;
  onReject: () => void;
  onAlwaysAllow: () => void;
  onAllowDomain: () => void;
}

export default function ApprovalActions({
  request,
  isLoading,
  isExpired,
  isAutoApproved,
  isSaveSkill,
  onApprove,
  onEdit,
  onReject,
  onAlwaysAllow,
  onAllowDomain,
}: ApprovalActionsProps) {
  const t = useTranslations('toolApproval');

  if (request.smartDenied) {
    return (
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={onApprove} disabled={isLoading || isExpired}>
          <ShieldAlert className="mr-1 h-3.5 w-3.5" />
          {t('smartDenied.overrideOnce')}
        </Button>
        <Button size="sm" variant="destructive" onClick={onReject} disabled={isLoading}>
          <MessageSquareX className="mr-1 h-3.5 w-3.5" />
          {t('reject')}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={onApprove} disabled={isLoading || isExpired || isAutoApproved}>
        <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
        {isAutoApproved ? t('autoApproving') : isSaveSkill ? t('saveSkill.approve') : t('approve')}
      </Button>
      {!isSaveSkill && (
        <Button size="sm" variant="secondary" onClick={onEdit} disabled={isLoading || isExpired}>
          <Pencil className="mr-1 h-3.5 w-3.5" />
          {t('edit')}
        </Button>
      )}
      <Button size="sm" variant="outline" onClick={onReject} disabled={isLoading}>
        <MessageSquareX className="mr-1 h-3.5 w-3.5" />
        {isSaveSkill ? t('saveSkill.deny') : t('reject')}
      </Button>
      {!isSaveSkill && !request.hideAllowAlways && (
        <Button
          size="sm"
          variant="ghost"
          onClick={onAlwaysAllow}
          disabled={isLoading || isExpired}
          className="text-xs text-amber-600 hover:text-amber-700"
        >
          {t('allowAlways')}
        </Button>
      )}
      {request.domainApproval && request.domains && request.domains.length > 0 && (
        <Button
          size="sm"
          variant="ghost"
          onClick={onAllowDomain}
          disabled={isLoading || isExpired}
          className="text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
          title={t('domain.allowDomainDesc')}
        >
          <Globe className="mr-1 h-3.5 w-3.5" />
          {t('domain.allowDomain')}
        </Button>
      )}
    </div>
  );
}
