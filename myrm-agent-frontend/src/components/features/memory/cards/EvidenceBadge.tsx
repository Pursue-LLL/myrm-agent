'use client';

/**
 * [INPUT]
 * @/components/features/memory/drawers/EvidenceDrawer::EvidenceDrawer
 * lucide-react::FileText, Lock, MessageSquare
 *
 * [OUTPUT]
 * EvidenceBadge: 轻量级可点击证据胶囊徽章（带侧边抽屉唤起与纠偏操作）
 *
 * [POS]
 * 记忆卡片与治理视图中的通用证据徽标组件。支持 Hover 查看简报，Click 就地呼出全功能证据抽屉。
 */

import { memo, useState } from 'react';
import { FileText, Lock, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { EvidenceDrawer } from '../drawers/EvidenceDrawer';

export interface EvidenceBadgeProps {
  sourceId?: string | null;
  messageId?: string | null;
  channelId?: string | null;
  quoteSnippet?: string | null;
  authorName?: string | null;
  authorId?: string | null;
  isUserLocked?: boolean;
  className?: string;
  onMarkFalsePositive?: () => Promise<void>;
  onCorrectAndLock?: (newContent: string) => Promise<void>;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export const EvidenceBadge = memo(function EvidenceBadge({
  sourceId,
  messageId,
  channelId,
  quoteSnippet,
  authorName,
  authorId,
  isUserLocked = false,
  className,
  onMarkFalsePositive,
  onCorrectAndLock,
  t,
}: EvidenceBadgeProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const hasEvidence = Boolean(sourceId || messageId || channelId || quoteSnippet);
  if (!hasEvidence) return null;

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setDrawerOpen(true);
        }}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-all duration-200',
          'border-primary/25 bg-primary/5 text-primary hover:border-primary/50 hover:bg-primary/10',
          isUserLocked && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
          className,
        )}
        title={t('commandCenter.evidence.badgeTooltip')}
      >
        <FileText className="h-3 w-3 shrink-0" />
        <span>{channelId ? `${channelId}` : t('commandCenter.evidence.badgeLabel')}</span>
        {isUserLocked && <Lock className="h-2.5 w-2.5 text-emerald-600 dark:text-emerald-400" />}
      </button>

      <EvidenceDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sourceId={sourceId}
        messageId={messageId}
        channelId={channelId}
        quoteSnippet={quoteSnippet}
        authorName={authorName}
        authorId={authorId}
        isUserLocked={isUserLocked}
        onMarkFalsePositive={onMarkFalsePositive}
        onCorrectAndLock={onCorrectAndLock}
        t={t}
      />
    </>
  );
});
