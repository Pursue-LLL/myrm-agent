'use client';

import { useMemo, useState, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Check, Clock3, Edit3, ShieldAlert, X } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import ReactDiffViewer from 'react-diff-viewer';
import { useTheme } from 'next-themes';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCase } from '@/services/skill-growth';
import { LazyMonacoDiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import type { DiffOnMount } from '@monaco-editor/react';
import { useIsMobile } from '@/hooks/useMediaQuery';

interface SkillGrowthCaseCardProps {
  item: SkillGrowthCase;
  isProcessing: boolean;
  onApprove: () => Promise<void>;
  onApproveShadow?: () => Promise<void>;
  onReject: (reason?: string) => Promise<void>;
  onRevise?: (evolvedContent: string) => Promise<void>;
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
  onApprove,
  onApproveShadow,
  onReject,
  onRevise,
}: SkillGrowthCaseCardProps) {
  const t = useTranslations('settings.skills.growth');
  const { theme } = useTheme();
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const modifiedEditorRef = useRef<{ getValue: () => string } | null>(null);

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
          <p className="text-sm text-muted-foreground">{item.summary}</p>
          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Clock3 className="h-3.5 w-3.5" />
              {createdAt}
            </span>
            {item.confidence !== null && (
              <span className="inline-flex items-center gap-1">
                <IconGlow className="h-3.5 w-3.5" />
                {t('confidence', { value: (item.confidence * 100).toFixed(1) })}
              </span>
            )}
            {item.testPassed !== null && (
              <span className="inline-flex items-center gap-1">
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
            <Button size="sm" onClick={onApprove} disabled={isProcessing}>
              <Check className="mr-2 h-4 w-4" />
              {approveLabel}
            </Button>
          </div>
        )}
      </div>

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

      {item.triggerCondition && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('triggerCondition')}</p>
          <p className="mt-1 text-sm whitespace-pre-wrap">{item.triggerCondition}</p>
        </div>
      )}

      {item.skillSteps && (
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

      {!isEditing && showDiff && (
        <div className="mt-4 overflow-hidden rounded-xl border">
          <ReactDiffViewer
            oldValue={item.originalContent ?? ''}
            newValue={item.proposedContent ?? ''}
            splitView
            useDarkTheme={isDark}
            leftTitle={t('original')}
            rightTitle={t('proposed')}
          />
        </div>
      )}

      {!isEditing && !showDiff && item.proposedContent && (
        <div className="mt-4 rounded-xl border bg-muted/20 p-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('proposed')}</p>
          <pre className="mt-1 whitespace-pre-wrap text-sm text-foreground">{item.proposedContent}</pre>
        </div>
      )}

      {item.trajectory && (
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
