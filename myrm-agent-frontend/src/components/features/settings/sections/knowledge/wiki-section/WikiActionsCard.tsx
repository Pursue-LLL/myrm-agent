'use client';

/**
 * [INPUT] ./useWikiMaintenance::WikiMaintenanceController (POS: 编译、维护、修复与重建索引的状态和动作), ./useWikiOverviewData::WikiOverviewData (POS: 编译运行与 ingest 快照), ../WikiCompilePhaseBar (POS: 编译阶段条)
 * [OUTPUT] WikiActionsCard: “操作”卡: 编译熔断暂停时的恢复横幅、编译阶段条、维护模式选择与提示、编译 / 维护 (可停止) / 修复页面类型 / 修复发布状态 / 重建向量索引按钮, 以及重建索引的错误清单
 * [POS] 总览页的操作卡; 编译进行中 (队列 processing > 0 或本页刚触发) 时禁用维护与重建索引。
 */

import { useTranslations } from 'next-intl';
import { IconDatabase, IconGlow, IconStop, IconWrench } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { WikiCompilePhaseBar } from '../WikiCompilePhaseBar';
import type { WikiMaintenanceController } from './useWikiMaintenance';
import type { WikiOverviewData } from './useWikiOverviewData';

interface WikiActionsCardProps {
  maintenance: WikiMaintenanceController;
  overview: Pick<WikiOverviewData, 'compileRun' | 'ingestSnapshot'>;
  onViewQueue: () => void;
}

export function WikiActionsCard({ maintenance, overview, onViewQueue }: WikiActionsCardProps) {
  const t = useTranslations('settings.wiki');
  const { compileRun, ingestSnapshot } = overview;
  const {
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
  } = maintenance;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconWrench className="w-5 h-5" />
          {t('actions.title')}
        </CardTitle>
        <CardDescription>{t('actions.description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {compileRun?.state === 'paused' && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-3">
            <div className="text-sm font-medium text-amber-800 dark:text-amber-200">{t('compileRun.pausedTitle')}</div>
            <p className="text-sm text-amber-900/80 dark:text-amber-100/80">
              {compileRun.pause_reason || t('compileRun.pausedDefault')}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={isResumingCompile}
                onClick={() => void handleResumeCompile()}
              >
                {isResumingCompile ? t('compileRun.resuming') : t('compileRun.resume')}
              </Button>
              <Button size="sm" variant="ghost" onClick={onViewQueue}>
                {t('compileRun.viewQueue')}
              </Button>
            </div>
          </div>
        )}
        {compileRun && compileRun.state !== 'paused' && (
          <WikiCompilePhaseBar
            compileRun={compileRun}
            pendingCount={ingestSnapshot?.stats.pending ?? 0}
            processingCount={ingestSnapshot?.stats.processing ?? 0}
            forceVisible={isCompiling}
          />
        )}
        <div className="space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <label htmlFor="wiki-maintain-mode" className="text-sm font-medium text-foreground">
              {t('actions.maintainModeLabel')}
            </label>
            <Select value={maintainMode} onValueChange={(value) => setMaintainMode(value as 'structural' | 'full')}>
              <SelectTrigger id="wiki-maintain-mode" className="w-full sm:w-64">
                <SelectValue placeholder={t('actions.maintainModeStructural')}>
                  {maintainMode === 'full' ? t('actions.maintainModeFull') : t('actions.maintainModeStructural')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="structural">{t('actions.maintainModeStructural')}</SelectItem>
                <SelectItem value="full">{t('actions.maintainModeFull')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-muted-foreground">
            {isWikiCompileBusy
              ? t('actions.maintainCompileBusyHint')
              : maintainMode === 'full'
                ? t('actions.maintainModeFullHint')
                : t('actions.maintainModeStructuralHint')}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-4">
          <Button onClick={handleCompile} disabled={isCompiling || compileRun?.state === 'paused'} className="flex-1">
            <IconGlow className="w-4 h-4 mr-2" />
            {isWikiCompileBusy ? t('compiling') : t('actions.compile')}
          </Button>
          <div className="flex flex-1 gap-2">
            <Button
              onClick={handleMaintain}
              disabled={isMaintaining || isWikiCompileBusy}
              variant="outline"
              className="min-w-0 flex-1"
              data-testid="wiki-maintain-button"
            >
              <IconWrench className="w-4 h-4 mr-2 shrink-0" />
              <span className="truncate">
                {isMaintaining
                  ? maintainProgressLabel
                    ? t(maintainProgressLabel.key, maintainProgressLabel.values)
                    : t('maintaining')
                  : t('actions.maintain')}
              </span>
            </Button>
            {isMaintaining && (canCancelMaintain || isCancellingMaintain) && (
              <Button
                onClick={() => void handleCancelMaintain()}
                disabled={isCancellingMaintain}
                variant="outline"
                className="shrink-0"
                data-testid="wiki-maintain-cancel-button"
              >
                <IconStop className="w-4 h-4 mr-2" />
                {isCancellingMaintain ? t('actions.maintainCancelling') : t('actions.maintainCancel')}
              </Button>
            )}
          </div>
          <Button onClick={handleRepairPageTypes} disabled={isRepairingTypes} variant="outline" className="flex-1">
            <IconWrench className="w-4 h-4 mr-2" />
            {isRepairingTypes ? t('repairingTypes') : t('actions.repairPageTypes')}
          </Button>
          <Button
            onClick={handleRepairPublication}
            disabled={isRepairingPublication}
            variant="outline"
            className="flex-1"
          >
            <IconWrench className="w-4 h-4 mr-2" />
            {isRepairingPublication ? t('repairingPublication') : t('actions.repairPublication')}
          </Button>
          <Button
            onClick={() => void handleReindexVectors()}
            disabled={isReindexingVectors || isWikiCompileBusy}
            variant="outline"
            className="flex-1"
          >
            <IconDatabase className="w-4 h-4 mr-2" />
            {isReindexingVectors ? t('reindexingVectors') : t('actions.reindexVectors')}
          </Button>
        </div>
        {reindexErrors.length > 0 ? (
          <div
            className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm"
            data-testid="wiki-reindex-errors"
          >
            <p className="font-medium text-amber-800 dark:text-amber-200">
              {t('reindexErrorsTitle', { count: reindexErrors.length })}
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
              {reindexErrors.slice(0, 8).map((entry, index) => (
                <li key={`${index}-${entry}`} className="break-all">
                  {entry}
                </li>
              ))}
            </ul>
            {reindexErrors.length > 8 ? (
              <p className="mt-2 text-xs text-muted-foreground">
                {t('reindexErrorsTruncated', { count: reindexErrors.length - 8 })}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
