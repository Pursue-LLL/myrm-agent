/**
 * [INPUT] SkillGrowthCase via @/services/skill-growth
 * [OUTPUT] SkillGrowthCaseCard: 技能进化提案卡片（Simple/Detailed 双视图、Monaco DiffEditor 就地修订、审批/拒绝）; SkillGrowthViewMode type
 * [POS] features/skills 单个技能进化提案的展示与交互卡片
 */
'use client';

import { useMemo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { CalendarClock, Check, ChevronDown, ChevronUp, Clock3, Edit3, ExternalLink, ShieldAlert, X } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { TextDiffViewer } from '@/lib/diff/TextDiffViewer';
import { useTheme } from 'next-themes';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCase } from '@/services/skill-growth';
import { LazyMonacoDiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import type { DiffOnMount } from '@monaco-editor/react';
import { useIsMobile } from '@/hooks/useMediaQuery';

export type SkillGrowthViewMode = 'simple' | 'detailed';

interface SkillGrowthCaseCardProps {
  item: SkillGrowthCase;
  isProcessing: boolean;
  viewMode?: SkillGrowthViewMode;
  onApprove: () => Promise<void>;
  onApproveShadow?: () => Promise<void>;
  onReject: (reason?: string) => Promise<void>;
  onRevise?: (evolvedContent: string) => Promise<void>;
  onCreateCron?: (scheduleHint: string) => Promise<void>;
}

const STATUS_STYLES: Record<
  SkillGrowthCase['status'],
  { badge: string; tone: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  PENDING_REVIEW: {
    badge: 'border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-300',
    tone: 'outline',
  },
  AUTO_APPLIED: {
    badge: 'border-emerald-300 text-emerald-700 dark:border-emerald-700 dark:text-emerald-300',
    tone: 'outline',
  },
  FAILED_SCAN: { badge: 'border-red-300 text-red-700 dark:border-red-700 dark:text-red-300', tone: 'outline' },
  BLOCKED_LOCKED: {
    badge: 'border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-300',
    tone: 'outline',
  },
  APPROVED: { badge: 'border-sky-300 text-sky-700 dark:border-sky-700 dark:text-sky-300', tone: 'outline' },
  REJECTED: { badge: 'border-rose-300 text-rose-700 dark:border-rose-700 dark:text-rose-300', tone: 'outline' },
  APPLY_FAILED: {
    badge: 'border-orange-300 text-orange-700 dark:border-orange-700 dark:text-orange-300',
    tone: 'outline',
  },
};

export default function SkillGrowthCaseCard({
  item,
  isProcessing,
  viewMode = 'detailed',
  onApprove,
  onApproveShadow,
  onReject,
  onRevise,
  onCreateCron,
}: SkillGrowthCaseCardProps) {
  const t = useTranslations('settings.skills.growth');
  const { theme } = useTheme();
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const [expandedInSimple, setExpandedInSimple] = useState(false);
  const modifiedEditorRef = useRef<{ getValue: () => string } | null>(null);
  const isSimple = viewMode === 'simple';

  const isDark = theme === 'dark';
  const isMobile = useIsMobile();
  const statusStyle = STATUS_STYLES[item.status];
  const statusLabel = t(`status.${item.status}` as Parameters<typeof t>[0]);
  const sourceLabel = item.source === 'draft' ? t('source.backgroundReview') : t('source.manualEvolution');
  const createdAt = useMemo(() => new Date(item.createdAt).toLocaleString(), [item.createdAt]);
  const showDiff = Boolean(item.originalContent !== null && item.proposedContent);
  const showReviewActions = item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED';
  const approveLabel = item.status === 'APPLY_FAILED' ? t('actions.retryApply') : t('actions.approve');
  const runtimeFailure = item.runtimeFailure;
  const canRevise = showReviewActions && item.source === 'evolution' && onRevise;

  const handleReject = async () => {
    if (!showRejectInput) {
      setShowRejectInput(true);
      return;
    }
    await onReject(rejectionReason.trim() || undefined);
    setShowRejectInput(false);
    setRejectionReason('');
  };

  const handleStartEdit = useCallback(() => {
    setEditedContent(item.proposedContent ?? '');
    setIsEditing(true);
  }, [item.proposedContent]);

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
    if (!onRevise || !content.trim()) return;
    await onRevise(content);
    setIsEditing(false);
    setEditedContent('');
    modifiedEditorRef.current = null;
  }, [onRevise, editedContent]);

  return (
    <div className="rounded-2xl border bg-background p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-foreground">{item.skillName}</h3>
            <Badge variant={statusStyle.tone} className={cn('text-[11px]', statusStyle.badge)}>
              {statusLabel}
            </Badge>
            <Badge variant="secondary" className="text-[11px]">
              {sourceLabel}
            </Badge>
            <Badge variant="outline" className="text-[11px]">
              {item.growthType}
            </Badge>
          </div>
          <p className={cn('text-muted-foreground', isSimple ? 'text-base font-medium text-foreground' : 'text-sm')}>
            {item.summary}
          </p>
          <div className={cn('flex flex-wrap items-center gap-3 text-muted-foreground', isSimple ? 'text-sm' : 'text-xs')}>
            <span className="inline-flex items-center gap-1">
              <Clock3 className="h-3.5 w-3.5" />
              {createdAt}
            </span>
            {item.chatId && (
              <Link
                href={`/${item.chatId}`}
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                {t('viewSourceChat')}
              </Link>
            )}
            {item.confidence !== null && (
              <span className={cn('inline-flex items-center gap-1', isSimple && (
                item.confidence >= 0.8 ? 'text-emerald-600 dark:text-emerald-400' :
                item.confidence >= 0.5 ? 'text-amber-600 dark:text-amber-400' :
                'text-red-600 dark:text-red-400'
              ))}>
                <IconGlow className="h-3.5 w-3.5" />
                {t('confidence', { value: (item.confidence * 100).toFixed(1) })}
              </span>
            )}
            {item.testPassed !== null && (
              <span className={cn('inline-flex items-center gap-1', isSimple && (
                item.testPassed ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
              ))}>
                <ShieldAlert className="h-3.5 w-3.5" />
                {item.testPassed ? t('testPassed') : t('testFailed')}
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
                onClick={handleStartEdit}
                disabled={isProcessing}
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
            {item.source === 'evolution' && onApproveShadow && (
              <Button variant="secondary" size="sm" onClick={onApproveShadow} disabled={isProcessing}>
                <Check className="mr-2 h-4 w-4" />
                {t('actions.approveShadow')}
              </Button>
            )}
            {item.growthType === 'cron_suggestion' && onCreateCron && item.formMetadata?.scheduleHint ? (
              <Button
                size="sm"
                className="bg-violet-600 hover:bg-violet-700 text-white"
                onClick={() => onCreateCron(item.formMetadata!.scheduleHint!)}
                disabled={isProcessing}
              >
                <CalendarClock className="mr-2 h-4 w-4" />
                {t('actions.createCron')}
              </Button>
            ) : (
              <Button size="sm" onClick={onApprove} disabled={isProcessing}>
                <Check className="mr-2 h-4 w-4" />
                {approveLabel}
              </Button>
            )}
          </div>
        )}
      </div>

      {item.growthType === 'cron_suggestion' && item.formMetadata?.scheduleHint && (
        <div className="mt-4 rounded-xl border border-violet-300/50 bg-violet-50/60 p-3 dark:border-violet-900/40 dark:bg-violet-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('cronSuggestion.title')}
          </p>
          <div className="mt-2 flex items-center gap-2 text-sm text-foreground">
            <CalendarClock className="h-4 w-4 text-violet-600 dark:text-violet-400" />
            <span>{item.formMetadata.scheduleHint}</span>
          </div>
          {item.formMetadata.formReasoning && (
            <p className="mt-2 text-xs text-muted-foreground">{item.formMetadata.formReasoning}</p>
          )}
        </div>
      )}

      {runtimeFailure && (
        <div className="mt-4 rounded-xl border border-sky-300/50 bg-sky-50/60 p-3 dark:border-sky-900/40 dark:bg-sky-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('runtimeFailure.title')}
          </p>
          <div className="mt-2 grid gap-2 text-sm text-foreground md:grid-cols-2">
            <span className="min-w-0 truncate">{t('runtimeFailure.tool', { value: runtimeFailure.tool_name })}</span>
            <span className="min-w-0 truncate">
              {t('runtimeFailure.count', { value: runtimeFailure.failure_count })}
            </span>
            <span className="min-w-0 truncate">
              {t('runtimeFailure.confidence', {
                value: (runtimeFailure.attribution_confidence * 100).toFixed(0),
              })}
            </span>
            {runtimeFailure.loop_kind && (
              <span className="min-w-0 truncate">
                {t('runtimeFailure.loopKind', { value: runtimeFailure.loop_kind })}
              </span>
            )}
          </div>
          <p className="mt-2 break-words font-mono text-xs text-sky-900 dark:text-sky-100">
            {runtimeFailure.error_signature}
          </p>
        </div>
      )}

      {item.reasonCode?.startsWith('risk:') && (
        <div className="mt-4 rounded-xl border border-amber-300/50 bg-amber-50/60 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('riskInterceptionTitle')}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {item.reasonCode
              .slice(5)
              .split(',')
              .map((signal) => (
                <Badge
                  key={signal}
                  variant="outline"
                  className="text-[11px] border-amber-400 text-amber-700 dark:border-amber-700 dark:text-amber-300"
                >
                  {signal}
                </Badge>
              ))}
          </div>
          {item.remediation && <p className="mt-2 text-sm text-muted-foreground">{item.remediation}</p>}
        </div>
      )}

      {item.applyError && (
        <div className="mt-4 rounded-xl border border-orange-300/50 bg-orange-50/60 p-3 dark:border-orange-900/40 dark:bg-orange-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('applyFailureTitle')}</p>
          <p className="mt-1 text-sm text-foreground">{item.applyError}</p>
          {item.remediation && !item.reasonCode?.startsWith('risk:') && (
            <p className="mt-2 text-sm text-muted-foreground">{item.remediation}</p>
          )}
        </div>
      )}

      {isSimple && !expandedInSimple && (showDiff || item.proposedContent) && (
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setExpandedInSimple(true)}
        >
          <ChevronDown className="h-3.5 w-3.5" />
          {t('viewChanges')}
        </button>
      )}
      {isSimple && expandedInSimple && (
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setExpandedInSimple(false)}
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

      {(!isSimple || expandedInSimple) && item.triggerCondition && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('triggerCondition')}</p>
          <p className="mt-1 text-sm whitespace-pre-wrap">{item.triggerCondition}</p>
        </div>
      )}

      {(!isSimple || expandedInSimple) && item.skillSteps && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('skillSteps')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-sm text-foreground">{item.skillSteps}</pre>
        </div>
      )}

      {isEditing && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('actions.reviseLabel')}</p>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={handleCancelEdit} disabled={isProcessing}>
                <X className="mr-1 h-3.5 w-3.5" />
                {t('actions.cancelRevise')}
              </Button>
              <Button size="sm" onClick={handleSaveRevision} disabled={isProcessing || !editedContent.trim()}>
                <Check className="mr-1 h-3.5 w-3.5" />
                {t('actions.saveRevision')}
              </Button>
            </div>
          </div>
          <div className="rounded-xl border overflow-hidden bg-background h-[300px] md:h-[400px]">
            <LazyMonacoDiffEditor
              height="100%"
              original={item.originalContent ?? ''}
              modified={editedContent}
              theme={isDark ? 'vs-dark' : 'light'}
              onMount={handleDiffEditorMount}
              options={{
                readOnly: false,
                renderSideBySide: !isMobile,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                lineNumbersMinChars: 3,
                padding: { top: 12, bottom: 12 },
                originalEditable: false,
              }}
            />
          </div>
        </div>
      )}

      {(!isSimple || expandedInSimple) && !isEditing && showDiff && (
        <div className="mt-4 overflow-hidden rounded-xl border">
          <div className="bg-muted px-3 py-2 border-b flex justify-between text-xs font-medium">
            <span className="text-red-500">{t('original')}</span>
            <span className="text-green-500">{t('proposed')}</span>
          </div>
          <TextDiffViewer
            oldValue={item.originalContent ?? ''}
            newValue={item.proposedContent ?? ''}
            filePath="skill.md"
            defaultViewMode={isMobile ? 'unified' : 'split'}
          />
        </div>
      )}

      {(!isSimple || expandedInSimple) && !isEditing && !showDiff && item.proposedContent && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('proposed')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-sm text-foreground">{item.proposedContent}</pre>
        </div>
      )}

      {(!isSimple || expandedInSimple) && item.trajectory && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('trajectoryAnalysis')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-xs text-foreground font-mono overflow-x-auto">
            {item.trajectory}
          </pre>
        </div>
      )}
    </div>
  );
}
