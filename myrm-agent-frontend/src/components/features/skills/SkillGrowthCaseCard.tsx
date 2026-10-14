/**
 * [INPUT] SkillGrowthCaseSummary via @/services/skill/growth; detail fetched on expand; ./growth-card (头部徽章、证据面板、修订编辑器)
 * [OUTPUT] SkillGrowthCaseCard: 技能进化提案卡片（Simple/Detailed 双视图、Monaco DiffEditor 就地修订、审批/拒绝）; SkillGrowthViewMode type
 * [POS] features/skills 单个技能进化提案的展示与交互卡片；持有展开、详情加载、修订与拒绝的交互状态
 */
'use client';

import { useMemo, useState, useCallback, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Check, ChevronDown, ChevronUp, Clock3, Edit3, ExternalLink, Loader2, X } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { GrowthCaseEvidence } from '@/components/features/skills/growth-card/GrowthCaseEvidence';
import { GrowthCaseTitleRow } from '@/components/features/skills/growth-card/GrowthCaseTitleRow';
import { GrowthRevisionEditor } from '@/components/features/skills/growth-card/GrowthRevisionEditor';
import { TextDiffViewer } from '@/lib/diff/TextDiffViewer';
import { useTheme } from 'next-themes';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import {
  getSkillGrowthCaseDetail,
  type SkillGrowthCaseDetail,
  type SkillGrowthCaseSummary,
} from '@/services/skill/growth';
import type { DiffOnMount } from '@monaco-editor/react';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';

export type SkillGrowthViewMode = 'simple' | 'detailed';

interface SkillGrowthCaseCardProps {
  item: SkillGrowthCaseSummary;
  isProcessing: boolean;
  viewMode?: SkillGrowthViewMode;
  onApprove: () => Promise<void>;
  onReject: (reason?: string) => Promise<void>;
  onRevise?: (evolvedContent: string) => Promise<void>;
}

export default function SkillGrowthCaseCard({
  item,
  isProcessing,
  viewMode = 'detailed',
  onApprove,
  onReject,
  onRevise,
}: SkillGrowthCaseCardProps) {
  const t = useTranslations('settings.skills.growth');
  const { theme } = useTheme();
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const [contentExpanded, setContentExpanded] = useState(false);
  const [detail, setDetail] = useState<SkillGrowthCaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const modifiedEditorRef = useRef<{ getValue: () => string } | null>(null);
  const isSimple = viewMode === 'simple';

  const isDark = theme === 'dark';
  const isMobile = useIsMobile();
  const createdAt = useMemo(() => new Date(item.createdAt).toLocaleString(), [item.createdAt]);
  const showReviewActions = item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED';
  const approveLabel = item.status === 'APPLY_FAILED' ? t('actions.retryApply') : t('actions.approve');
  const canRevise = showReviewActions && item.source === 'evolution' && onRevise;

  const hasExpandableContent = item.hasDiff || item.hasTrajectory || item.hasTriggerCondition || item.hasSkillSteps;

  const originalContent = detail?.originalContent ?? null;
  const proposedContent = detail?.proposedContent ?? null;
  const showDiff = Boolean(originalContent !== null && proposedContent);

  useEffect(() => {
    setDetail(null);
    setDetailError(null);
    setContentExpanded(false);
    setIsEditing(false);
    setEditedContent('');
  }, [item.id]);

  const loadDetail = useCallback(async (): Promise<SkillGrowthCaseDetail | null> => {
    if (detail !== null) {
      return detail;
    }
    setDetailLoading(true);
    setDetailError(null);
    try {
      const loaded = await getSkillGrowthCaseDetail(item.id);
      setDetail(loaded);
      return loaded;
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : t('detailLoadFailed');
      setDetailError(message);
      return null;
    } finally {
      setDetailLoading(false);
    }
  }, [detail, item.id, t]);

  const handleExpandContent = useCallback(async () => {
    if (!contentExpanded) {
      setContentExpanded(true);
      if (hasExpandableContent) {
        await loadDetail();
      }
      return;
    }
    setContentExpanded(false);
    setIsEditing(false);
  }, [contentExpanded, hasExpandableContent, loadDetail]);

  const handleReject = async () => {
    if (!showRejectInput) {
      setShowRejectInput(true);
      return;
    }
    await onReject(rejectionReason.trim() || undefined);
    setShowRejectInput(false);
    setRejectionReason('');
  };

  const handleStartEdit = useCallback(async () => {
    const loaded = await loadDetail();
    if (loaded === null) {
      return;
    }
    setEditedContent(loaded.proposedContent ?? '');
    setContentExpanded(true);
    setIsEditing(true);
  }, [loadDetail]);

  const handleCancelEdit = useCallback(() => {
    setIsEditing(false);
    setEditedContent('');
    modifiedEditorRef.current = null;
  }, []);

  const handleDiffEditorMount: DiffOnMount = useCallback((editor) => {
    const modifiedEditor = editor.getModifiedEditor();
    modifiedEditorRef.current = modifiedEditor;
    modifiedEditor.onDidChangeModelContent(() => {
      setEditedContent(modifiedEditor.getValue());
    });
  }, []);

  const handleSaveRevision = useCallback(async () => {
    const content = modifiedEditorRef.current?.getValue() ?? editedContent;
    if (!onRevise || !content.trim()) {
      return;
    }
    await onRevise(content);
    setIsEditing(false);
    setEditedContent('');
    modifiedEditorRef.current = null;
    setDetail(null);
  }, [onRevise, editedContent]);

  const showContentPanel = !isSimple || contentExpanded;

  return (
    <div className="rounded-2xl border bg-background p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 space-y-2">
          <GrowthCaseTitleRow item={item} isSimple={isSimple} />
          <p className={cn('text-muted-foreground', isSimple ? 'text-base font-medium text-foreground' : 'text-sm')}>
            {item.summary}
          </p>
          <div
            className={cn('flex flex-wrap items-center gap-3 text-muted-foreground', isSimple ? 'text-sm' : 'text-xs')}
          >
            <span className="inline-flex items-center gap-1">
              <Clock3 className="h-3.5 w-3.5" />
              {createdAt}
            </span>
            {item.chatId && (
              <Link href={`/${item.chatId}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                <ExternalLink className="h-3.5 w-3.5" />
                {t('viewSourceChat')}
              </Link>
            )}
            {item.confidence !== null && (
              <span
                className={cn(
                  'inline-flex items-center gap-1',
                  isSimple &&
                    (item.confidence >= 0.8
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : item.confidence >= 0.5
                        ? 'text-amber-600 dark:text-amber-400'
                        : 'text-red-600 dark:text-red-400'),
                )}
              >
                <IconGlow className="h-3.5 w-3.5" />
                {t('confidence', { value: (item.confidence * 100).toFixed(1) })}
              </span>
            )}
          </div>
        </div>

        {showReviewActions && (
          <div className="flex shrink-0 items-center gap-2">
            {canRevise && !isEditing && (
              <Button
                variant="outline"
                size="sm"
                className="border-blue-300 text-blue-700 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950/30"
                onClick={() => void handleStartEdit()}
                disabled={isProcessing || detailLoading}
              >
                <Edit3 className="mr-2 h-4 w-4" />
                {t('actions.revise')}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/30"
              onClick={handleReject}
              disabled={isProcessing}
            >
              <X className="mr-2 h-4 w-4" />
              {showRejectInput ? t('actions.confirmReject') : t('actions.reject')}
            </Button>
            <Button size="sm" onClick={onApprove} disabled={isProcessing}>
              <Check className="mr-2 h-4 w-4" />
              {approveLabel}
            </Button>
          </div>
        )}
      </div>

      <GrowthCaseEvidence item={item} />

      {hasExpandableContent && !contentExpanded && (
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => void handleExpandContent()}
          disabled={detailLoading}
        >
          {detailLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ChevronDown className="h-3.5 w-3.5" />}
          {t('viewChanges')}
        </button>
      )}
      {hasExpandableContent && contentExpanded && (
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => void handleExpandContent()}
        >
          <ChevronUp className="h-3.5 w-3.5" />
          {t('hideChanges')}
        </button>
      )}

      {showRejectInput && (
        <div className="mt-3">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">{t('rejectReasonLabel')}</label>
          <textarea
            value={rejectionReason}
            onChange={(event) => setRejectionReason(event.target.value)}
            className="min-h-24 w-full rounded-xl border bg-muted/20 px-3 py-2 text-sm outline-none ring-0 transition-colors focus:border-primary"
            placeholder={t('rejectReasonPlaceholder')}
          />
        </div>
      )}

      {showContentPanel && detailLoading && (
        <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('loadingDetail')}
        </div>
      )}

      {showContentPanel && detailError && (
        <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {detailError}
        </div>
      )}

      {showContentPanel && detail && detail.triggerCondition && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('triggerCondition')}</p>
          <p className="mt-1 text-sm whitespace-pre-wrap">{detail.triggerCondition}</p>
        </div>
      )}

      {showContentPanel && detail && detail.skillSteps && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('skillSteps')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-sm text-foreground">{detail.skillSteps}</pre>
        </div>
      )}

      {isEditing && detail && (
        <GrowthRevisionEditor
          originalContent={originalContent ?? ''}
          editedContent={editedContent}
          isProcessing={isProcessing}
          isDark={isDark}
          isMobile={isMobile}
          onMount={handleDiffEditorMount}
          onCancel={handleCancelEdit}
          onSave={() => void handleSaveRevision()}
        />
      )}

      {showContentPanel && !isEditing && detail && showDiff && (
        <div className="mt-4 overflow-hidden rounded-xl border">
          <div className="bg-muted px-3 py-2 border-b flex justify-between text-xs font-medium">
            <span className="text-red-500">{t('original')}</span>
            <span className="text-green-500">{t('proposed')}</span>
          </div>
          <TextDiffViewer
            oldValue={originalContent ?? ''}
            newValue={proposedContent ?? ''}
            filePath="skill.md"
            defaultViewMode={isMobile ? 'unified' : 'split'}
          />
        </div>
      )}

      {showContentPanel && !isEditing && detail && !showDiff && proposedContent && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('proposed')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-sm text-foreground">{proposedContent}</pre>
        </div>
      )}

      {showContentPanel && detail && detail.trajectory && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('trajectoryAnalysis')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-xs text-foreground font-mono overflow-x-auto">
            {detail.trajectory}
          </pre>
        </div>
      )}
    </div>
  );
}
