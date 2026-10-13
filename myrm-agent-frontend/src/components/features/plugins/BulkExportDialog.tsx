/**
 * 智能体全量资产一键批量迁移与同步导出对话框
 *
 * [INPUT]
 * @/services/agent::AgentListItem (POS: 智能体列表项接口)
 * @/services/expertPackage::previewMultiExpertExport,downloadMultiExpertPackage,ExpertExportError,expertExportErrorCode,EXPERT_EXPORT_CHANGED_SINCE_PREVIEW,ExpertExportPreview,ExpertExportErrorCode (POS: 批量导出服务契约)
 * @/components/features/redaction/RedactionReview::RedactionReview (POS: 敏感词脱敏复核组件)
 * @/components/features/redaction/useRedactionDecisions::useRedactionDecisions,keepEveryFinding (POS: 脱敏决策状态机)
 * @/components/features/plugins/ExpertExportClosure::ExpertExportClosure (POS: 导出闭包资产概览)
 * @/components/features/plugins/BulkExportSelectStep::BulkExportSelectStep (POS: 智能体选择与配置子面板)
 * @/lib/utils/fileUtils::triggerDownload (POS: 浏览器文件下载触发器)
 *
 * [OUTPUT]
 * BulkExportDialog 组件：承载多智能体资产依赖聚合、闭包审查、脱敏核对与 ZIP 导出的全流程向导。
 *
 * [POS]
 * 智能体模块的批量导出主对话框，负责调度选择、扫描与下载阶段。
 */

'use client';

import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowLeft, Package } from 'lucide-react';

import {
  IconAlertTriangle,
  IconArrowRight,
  IconCheckCircle,
  IconDownload,
  IconLoader,
} from '@/components/features/icons/PremiumIcons';
import RedactionReview from '@/components/features/redaction/RedactionReview';
import { keepEveryFinding, useRedactionDecisions } from '@/components/features/redaction/useRedactionDecisions';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils/classnameUtils';
import { triggerDownload } from '@/lib/utils/fileUtils';
import type { AgentListItem } from '@/services/agent';
import {
  downloadMultiExpertPackage,
  EXPERT_EXPORT_CHANGED_SINCE_PREVIEW,
  ExpertExportError,
  expertExportErrorCode,
  previewMultiExpertExport,
  type ExpertExportErrorCode,
  type ExpertExportPreview,
} from '@/services/expertPackage';
import { formatFileSize } from '@/types/artifact';

import { MOBILE_FULLSCREEN_DIALOG } from './dialogLayout';
import ExpertExportClosure from './ExpertExportClosure';
import BulkExportSelectStep from './BulkExportSelectStep';

interface BulkExportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: AgentListItem[];
}

type BulkExportStep = 'select' | 'preview';
type FailureKey = ExpertExportErrorCode | 'generic';

function diagnoseFailure(error: unknown): FailureKey {
  console.error('Multi-expert export request failed:', error);
  return expertExportErrorCode(error) ?? 'generic';
}

const BulkExportDialog = memo(({ open, onOpenChange, agents }: BulkExportDialogProps) => {
  const t = useTranslations('agent.expertExport');

  const customAgents = useMemo(() => agents.filter((a) => !a.is_built_in), [agents]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bundleName, setBundleName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [step, setStep] = useState<BulkExportStep>('select');

  const [preview, setPreview] = useState<ExpertExportPreview | null>(null);
  const [loadFailure, setLoadFailure] = useState<FailureKey | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const { ignored, reset, toggle, toggleAll } = useRedactionDecisions();

  useEffect(() => {
    if (open) {
      setSelectedIds(customAgents.map((a) => a.id));
      setBundleName('');
      setSearchQuery('');
      setStep('select');
      setPreview(null);
      setLoadFailure(null);
      reset();
    }
  }, [open, customAgents, reset]);

  const failureText = useCallback(
    (failure: FailureKey): string => {
      const key = `errors.${failure}` as Parameters<typeof t.has>[0];
      return t.has(key) ? t(key) : t('errors.generic');
    },
    [t],
  );

  const toggleSelectAgent = useCallback((id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  }, []);

  const handleSelectAll = useCallback(() => {
    setSelectedIds(customAgents.map((a) => a.id));
  }, [customAgents]);

  const handleClearAll = useCallback(() => {
    setSelectedIds([]);
  }, []);

  const loadPreview = useCallback(async () => {
    if (selectedIds.length === 0) {
      return;
    }
    setIsLoading(true);
    setPreview(null);
    setLoadFailure(null);
    reset();

    try {
      const loaded = await previewMultiExpertExport({
        agentIds: selectedIds,
        bundleName: bundleName.trim() || undefined,
      });
      if (loaded.build_error) {
        console.warn('Multi-expert package cannot be built:', loaded.build_error);
      }
      setPreview(loaded);
      setStep('preview');
    } catch (error) {
      setLoadFailure(diagnoseFailure(error));
    } finally {
      setIsLoading(false);
    }
  }, [selectedIds, bundleName, reset]);

  const findings = preview?.redactions ?? null;
  const hasFindings = findings !== null && Object.keys(findings).length > 0;
  const buildable = preview !== null && preview.build_error === null;

  const handleExport = useCallback(
    async (keepOriginal: boolean) => {
      if (!preview) {
        return;
      }
      setIsExporting(true);
      try {
        const { blob, filename } = await downloadMultiExpertPackage({
          agentIds: selectedIds,
          bundleName: bundleName.trim() || undefined,
          applyRedactions: !keepOriginal,
          ignoredRedactions: keepOriginal ? keepEveryFinding(findings ?? {}) : ignored,
          reviewDigest: preview.review_digest,
        });
        await triggerDownload(blob, filename || `${preview.plugin_name}_v${preview.version}.zip`);
        toast({
          title: t('exportSuccess'),
          description: t('bulk.exportReady'),
        });
        onOpenChange(false);
      } catch (error) {
        if (error instanceof ExpertExportError && error.code === EXPERT_EXPORT_CHANGED_SINCE_PREVIEW) {
          toast({ title: t('changedSinceReview'), variant: 'destructive' });
          void loadPreview();
          return;
        }
        toast({
          title: t('exportFailed'),
          description: failureText(diagnoseFailure(error)),
          variant: 'destructive',
        });
      } finally {
        setIsExporting(false);
      }
    },
    [preview, selectedIds, bundleName, findings, ignored, t, onOpenChange, loadPreview, failureText],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn('flex max-h-[85vh] flex-col sm:max-w-[720px]', MOBILE_FULLSCREEN_DIALOG)}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="h-5 w-5 text-primary" />
            <span>{t('bulk.title')}</span>
          </DialogTitle>
          <DialogDescription>
            {step === 'select' ? t('bulk.selectDescription') : t('bulk.reviewDescription')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 py-2">
          {step === 'select' ? (
            <BulkExportSelectStep
              customAgents={customAgents}
              selectedIds={selectedIds}
              searchQuery={searchQuery}
              bundleName={bundleName}
              loadFailureText={loadFailure ? failureText(loadFailure) : null}
              onSearchChange={setSearchQuery}
              onBundleNameChange={setBundleName}
              onToggleSelect={toggleSelectAgent}
              onSelectAll={handleSelectAll}
              onClearAll={handleClearAll}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-3">
              {isLoading && (
                <div className="flex flex-col items-center justify-center gap-3 py-10 text-muted-foreground">
                  <IconLoader className="h-8 w-8 animate-spin text-primary" />
                  <p className="text-sm">{t('scanning')}</p>
                </div>
              )}

              {preview && !isLoading && (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">
                      {preview.plugin_name} · v{preview.version}
                    </span>
                    {preview.package_bytes !== null && <span>{formatFileSize(preview.package_bytes)}</span>}
                  </div>

                  {preview.build_error && (
                    <Alert variant="destructive">
                      <IconAlertTriangle className="h-4 w-4" />
                      <AlertTitle>{t('buildErrorTitle')}</AlertTitle>
                      <AlertDescription className="break-words">{t('errors.package_rejected')}</AlertDescription>
                    </Alert>
                  )}

                  <div className={cn('overflow-y-auto pr-1', hasFindings ? 'max-h-[35vh] shrink-0' : 'min-h-0 flex-1')}>
                    <ExpertExportClosure preview={preview} />
                  </div>

                  {hasFindings ? (
                    <>
                      <Alert variant="destructive" className="bg-destructive/5">
                        <IconAlertTriangle className="h-4 w-4" />
                        <AlertTitle>{t('warningTitle')}</AlertTitle>
                        <AlertDescription>{t('warningDescription')}</AlertDescription>
                      </Alert>
                      <RedactionReview
                        findings={findings}
                        ignored={ignored}
                        onToggle={toggle}
                        onToggleAll={toggleAll}
                        disabled={isExporting}
                      />
                    </>
                  ) : (
                    <Alert className="border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30">
                      <IconCheckCircle className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                      <AlertTitle className="text-emerald-800 dark:text-emerald-300">{t('safeTitle')}</AlertTitle>
                      <AlertDescription className="text-emerald-700 dark:text-emerald-400">
                        {t('safeDescription')}
                      </AlertDescription>
                    </Alert>
                  )}

                  <div className="rounded-md border border-border/60 bg-muted/40 p-2.5 text-xs text-muted-foreground flex items-center gap-2">
                    <IconCheckCircle className="h-4 w-4 text-primary shrink-0" />
                    <span>{t('bulk.migrationHint')}</span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          {step === 'select' ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t('actions.cancel')}
              </Button>
              <Button onClick={() => void loadPreview()} disabled={selectedIds.length === 0 || isLoading}>
                {isLoading ? (
                  <IconLoader className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <IconArrowRight className="mr-2 h-4 w-4" />
                )}
                {t('bulk.next', { count: selectedIds.length })}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setStep('select')} disabled={isExporting}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                {t('bulk.back')}
              </Button>
              {buildable && hasFindings && (
                <Button
                  variant="destructive"
                  onClick={() => void handleExport(true)}
                  disabled={isExporting}
                  className="sm:mr-auto"
                >
                  {t('actions.exportOriginal')}
                </Button>
              )}
              {preview && (
                <Button onClick={() => void handleExport(false)} disabled={!buildable || isExporting}>
                  {isExporting ? (
                    <IconLoader className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <IconDownload className="mr-2 h-4 w-4" />
                  )}
                  {hasFindings ? t('actions.exportRedacted') : t('actions.export')}
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

BulkExportDialog.displayName = 'BulkExportDialog';

export default BulkExportDialog;
