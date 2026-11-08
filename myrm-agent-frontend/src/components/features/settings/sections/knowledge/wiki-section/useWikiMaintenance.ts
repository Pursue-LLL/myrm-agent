/**
 * [INPUT] @/services/wikiService::wikiService (POS: Wiki 编译、修复、重建索引接口), ../useWikiMaintainRun (POS: 维护运行的启动、轮询与取消), ../wiki/wikiSectionUtils (POS: 维护结果与失败提示映射), ./useWikiOverviewData (POS: 统计重载、编译运行与 ingest 快照)
 * [OUTPUT] useWikiMaintenance: 总览页“操作”区的状态与动作: 编译 / 恢复编译熔断、维护 (结构化 / 完整, 可取消)、修复页面类型与发布状态、重建向量索引
 * [POS] Wiki 面板的维护层: 手动编译只把原文入队并唤醒后台 worker, 队列排空时由 ingest 流提示一次完成; “编译中”以队列的 processing 为准, 编译进行中不允许启动维护与重建索引。
 */

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import { wikiService } from '@/services/wikiService';
import { useWikiMaintainRun, type WikiMaintainOutcome } from '../useWikiMaintainRun';
import {
  healthReportFromMaintainResponse,
  resolveMaintainFailureToastKey,
  resolveMaintainProgressLabel,
  resolveMaintainToast,
} from '../wiki/wikiSectionUtils';
import type { WikiOverviewData } from './useWikiOverviewData';

interface UseWikiMaintenanceParams {
  agentScopeId: string | null;
  overview: Pick<
    WikiOverviewData,
    | 'loadStats'
    | 'setCompileRun'
    | 'markCompileRequested'
    | 'setHealthReport'
    | 'setHealthReportExpanded'
    | 'bumpTreeSync'
    | 'ingestSnapshot'
  >;
  handleWikiTabChange: (tab: string) => void;
}

export function useWikiMaintenance({ agentScopeId, overview, handleWikiTabChange }: UseWikiMaintenanceParams) {
  const t = useTranslations('settings.wiki');
  const {
    loadStats,
    setCompileRun,
    markCompileRequested,
    setHealthReport,
    setHealthReportExpanded,
    bumpTreeSync,
    ingestSnapshot,
  } = overview;
  const [maintainMode, setMaintainMode] = useState<'structural' | 'full'>('structural');
  const [isCompiling, setIsCompiling] = useState(false);
  const [isResumingCompile, setIsResumingCompile] = useState(false);
  const [isRepairingTypes, setIsRepairingTypes] = useState(false);
  const [isRepairingPublication, setIsRepairingPublication] = useState(false);
  const [isReindexingVectors, setIsReindexingVectors] = useState(false);
  const [reindexErrors, setReindexErrors] = useState<string[]>([]);

  // `compileRun.state` is the circuit (running unless paused), not whether a compile is in flight: the queue says that.
  const isWikiCompileBusy = isCompiling || (ingestSnapshot?.stats.processing ?? 0) > 0;

  const handleCompile = async () => {
    setIsCompiling(true);
    try {
      const result = await wikiService.compileWiki(agentScopeId);
      setCompileRun(result.compile_run ?? null);
      markCompileRequested(result.pending > 0);
      if (result.compile_run?.state === 'paused') {
        toast.warning(result.compile_run.pause_reason || t('compileRun.pausedDefaultReason'));
        handleWikiTabChange('queue');
      } else if (result.pending > 0) {
        toast.message(t('success.compileStarted', { count: result.pending }));
      } else {
        toast.message(t('success.compileNothingNew'));
      }
      await loadStats();
    } catch (error) {
      console.error('Compile failed:', error);
      if (error instanceof ApiError && error.code === 409) {
        toast.error(t('errors.compileBlockedByDedup'));
        handleWikiTabChange('duplicateReview');
        return;
      }
      toast.error(t('errors.compileFailed'));
    } finally {
      setIsCompiling(false);
    }
  };

  const handleResumeCompile = async () => {
    setIsResumingCompile(true);
    try {
      await wikiService.resumeCompileCircuit(agentScopeId);
      toast.success(t('compileRun.resumeSuccess'));
      await loadStats();
    } catch (error) {
      console.error('Resume compile failed:', error);
      toast.error(t('compileRun.resumeFailed'));
    } finally {
      setIsResumingCompile(false);
    }
  };

  const handleMaintainFinished = async (outcome: WikiMaintainOutcome) => {
    if (outcome.kind === 'failure') {
      toast.error(t(resolveMaintainFailureToastKey(outcome.reason)));
      return;
    }
    const { result, mode } = outcome;
    const summary = resolveMaintainToast(result, outcome.kind === 'cancelled');
    toast[summary.variant](t(summary.key, summary.values));
    setHealthReportExpanded(true);
    await loadStats();
    setHealthReport((prev) =>
      healthReportFromMaintainResponse(result, mode, {
        duplicate_groups_pending: prev?.duplicate_groups_pending ?? 0,
        synthesis_pending: prev?.synthesis_pending ?? 0,
      }),
    );
    bumpTreeSync();
  };

  const {
    isRunning: isMaintaining,
    progress: maintainProgress,
    start: startMaintain,
    cancel: cancelMaintain,
    canCancel: canCancelMaintain,
    isCancelling: isCancellingMaintain,
  } = useWikiMaintainRun({ agentScopeId, onFinished: handleMaintainFinished });
  const maintainProgressLabel = resolveMaintainProgressLabel(maintainProgress);

  const handleMaintain = () => startMaintain(maintainMode);

  const handleCancelMaintain = async () => {
    try {
      await cancelMaintain();
    } catch (error) {
      console.error('Failed to cancel wiki maintenance:', error);
      toast.error(t('errors.maintainCancelFailed'));
    }
  };

  const handleRepairPageTypes = async () => {
    setIsRepairingTypes(true);
    try {
      const result = await wikiService.repairPageTypes(agentScopeId);
      if (result.success) {
        toast.success(t('success.repairTypesComplete', { count: result.files_repaired }));
      } else {
        toast.warning(result.message);
      }
      await loadStats();
    } catch (error) {
      console.error('Repair page types failed:', error);
      toast.error(t('errors.repairTypesFailed'));
    } finally {
      setIsRepairingTypes(false);
    }
  };

  const handleRepairPublication = async () => {
    setIsRepairingPublication(true);
    try {
      const result = await wikiService.repairPublication(agentScopeId);
      if (result.success) {
        const skippedDrafts = result.files_skipped_intentional_drafts ?? 0;
        toast.success(
          skippedDrafts > 0
            ? t('success.repairPublicationCompleteWithSkips', {
                repaired: result.files_repaired,
                reindexed: result.reindexed,
                skippedDrafts,
              })
            : t('success.repairPublicationComplete', {
                repaired: result.files_repaired,
                reindexed: result.reindexed,
              }),
        );
      } else {
        toast.warning(result.message);
      }
      await loadStats();
    } catch (error) {
      console.error('Repair publication failed:', error);
      toast.error(t('errors.repairPublicationFailed'));
    } finally {
      setIsRepairingPublication(false);
    }
  };

  const handleReindexVectors = async () => {
    setIsReindexingVectors(true);
    setReindexErrors([]);
    try {
      const result = await wikiService.reindexVectors(agentScopeId);
      setReindexErrors(result.errors ?? []);
      if (result.success) {
        toast.success(
          t('success.reindexVectorsComplete', {
            concepts: result.concepts_reindexed,
            sidecars: result.sidecars_reindexed,
            assets: result.assets_indexed,
          }),
        );
      } else {
        toast.warning(result.message);
      }
      await loadStats();
      bumpTreeSync();
    } catch (error) {
      console.error('Reindex wiki vectors failed:', error);
      toast.error(t('errors.reindexVectorsFailed'));
    } finally {
      setIsReindexingVectors(false);
    }
  };

  return {
    maintainMode,
    setMaintainMode,
    isCompiling,
    isResumingCompile,
    isRepairingTypes,
    isRepairingPublication,
    isReindexingVectors,
    reindexErrors,
    isWikiCompileBusy,
    isMaintaining,
    maintainProgressLabel,
    canCancelMaintain,
    isCancellingMaintain,
    handleCompile,
    handleResumeCompile,
    handleMaintain,
    handleCancelMaintain,
    handleRepairPageTypes,
    handleRepairPublication,
    handleReindexVectors,
  };
}

export type WikiMaintenanceController = ReturnType<typeof useWikiMaintenance>;
