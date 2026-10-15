'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 * ./MemoryCommandCenterAdvancedPanels::MemoryAdvancedVerifyPanels (POS: 个人大脑指挥中心验证面板)
 * ./MemoryCommandCenterObservationPanels::EventList (POS: 个人大脑指挥中心的只读观测面板)
 * ./MemoryCommandCenterGovernancePanels::MigrationPanel (POS: 个人大脑指挥中心的治理动作行、迁移覆盖与适配器状态面板)
 *
 * [OUTPUT]
 * ObserveSection, ActSection, VerifySection: Personal Brain Command Center section panels.
 *
 * [POS]
 * 个人大脑指挥中心基础展示面板。按观察、治理、验证分区展示记忆快照、证据、治理和运行状态，
 * 并为 migration adapter missing 状态提供迁移向导动作闭环；理解分区见 MemoryCommandCenterUnderstandSection。
 */

import { lazy, Suspense } from 'react';
import type {
  ConsolidationLastSummary,
  MemoryCommandCenterResponse,
  MemoryCommandDiagnosticHistoryItem,
  MemoryCommandDiagnosticRun,
  MemoryCommandGovernanceItem,
  MemoryCommandTimelineEvent,
} from '@/services/memory/commandCenter';
import { MemoryAdvancedVerifyPanels } from './MemoryCommandCenterAdvancedPanels';
import type { DoctorExecutableAction } from './MemoryCommandCenterDoctorPanel';
import { MemoryLayerGuide } from '../guides/MemoryLayerGuide';
import { ToolGuidancePanel } from './ToolGuidancePanel';
import { CognitiveClockPanel } from './CognitiveClockPanel';
import { DualLayerMemoryCard } from '@/components/agent/DualLayerMemoryCard';
import { FourLayerPromotionAuditCard } from './FourLayerPromotionAuditCard';
import { EbbinghausLifecycleCard } from './EbbinghausLifecycleCard';
import { SovereignMigrationInspectorCard } from './SovereignMigrationInspectorCard';
import { MEMORY_TYPES, translateSpaceKind, type MemoryTranslation } from './memoryCommandCenterFormat';
import { Panel, MetricTile, EmptyState } from './MemoryCommandCenterPrimitives';
import { EventList, RuntimePanel, CostPanel, ReplayRow } from './MemoryCommandCenterObservationPanels';
import { GovernanceRow, MigrationPanel, ConsolidationRollbackCard } from './MemoryCommandCenterGovernancePanels';

const MemoryHealthDashboard = lazy(() => import('../insights/MemoryHealthDashboard'));

export const ObserveSection = ({
  snapshot,
  liveStream,
  t,
  onEventClick,
}: {
  snapshot: MemoryCommandCenterResponse;
  liveStream: MemoryCommandTimelineEvent[];
  t: MemoryTranslation;
  onEventClick?: (event: MemoryCommandTimelineEvent) => void;
}) => (
  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
    <Panel title={t('commandCenter.typesTitle')}>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {MEMORY_TYPES.map((type) => (
          <MetricTile key={type} label={t(`types.${type}`)} value={snapshot.overview.by_type[type] ?? 0} dense />
        ))}
      </div>
      <MemoryLayerGuide />
    </Panel>
    <Panel title={t('commandCenter.liveStreamTitle')} liveHint={t('commandCenter.liveStreamHint')}>
      <EventList
        events={liveStream}
        t={t}
        emptyLabel={t('commandCenter.timelineEmpty')}
        live
        onEventClick={onEventClick}
      />
    </Panel>
    <Panel title={t('commandCenter.healthDashboard.totalScore')} className="xl:col-span-2">
      <Suspense
        fallback={
          <div className="flex items-center justify-center rounded-lg border border-dashed border-border/70 p-12">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        }
      >
        <MemoryHealthDashboard health={snapshot.health} t={t} />
      </Suspense>
    </Panel>
    <Panel title={t('commandCenter.spacesTitle')} className="xl:col-span-2">
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {snapshot.spaces.slice(0, 12).map((space) => (
          <div key={`${space.kind}:${space.namespace}`} className="rounded-lg border border-border/50 bg-accent/20 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">{space.label || space.namespace}</div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{space.namespace}</div>
              </div>
              <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                {translateSpaceKind(space.kind, t)}
              </span>
            </div>
            {space.kind === 'shared' && (
              <div className="mt-2 text-xs text-muted-foreground">
                {t('commandCenter.bindingCount', { count: space.binding_count })}
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  </div>
);

export const ActSection = ({
  snapshot,
  t,
  actionId,
  onAction,
  onDoctorAction,
  onRollbackImport,
  onOpenMigrationWizard,
  consolidationSummary,
  onConsolidationRollback,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  onAction: (item: MemoryCommandGovernanceItem, action: 'approve' | 'reject') => void;
  onDoctorAction: (action: DoctorExecutableAction) => void;
  onRollbackImport: (importBatchId: string) => void;
  onOpenMigrationWizard: (source: string) => void;
  consolidationSummary?: ConsolidationLastSummary | null;
  onConsolidationRollback?: () => void;
}) => (
  <div className="space-y-4">
    <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
      <div className="space-y-4">
        <Panel title={t('commandCenter.governanceTitle')}>
          {snapshot.governance.length ? (
            <div className="space-y-2">
              {snapshot.governance.map((item) => (
                <GovernanceRow
                  key={`${item.kind}:${item.id}`}
                  item={item}
                  t={t}
                  actionId={actionId}
                  onAction={onAction}
                />
              ))}
            </div>
          ) : (
            <EmptyState label={t('commandCenter.governanceEmpty')} />
          )}
        </Panel>
        {consolidationSummary?.available && (
          <Panel title={t('commandCenter.consolidationRollbackTitle')}>
            <ConsolidationRollbackCard
              summary={consolidationSummary}
              t={t}
              loading={actionId === 'consolidation:rollback'}
              onRollback={onConsolidationRollback}
            />
          </Panel>
        )}
      </div>
      <Panel title={t('commandCenter.migrationTitle')}>
        <MigrationPanel
          snapshot={snapshot}
          t={t}
          actionId={actionId}
          onDoctorAction={onDoctorAction}
          onRollbackImport={onRollbackImport}
          onOpenMigrationWizard={onOpenMigrationWizard}
        />
      </Panel>
    </div>
    <DualLayerMemoryCard />
    <FourLayerPromotionAuditCard />
    <EbbinghausLifecycleCard />
    <CognitiveClockPanel />
    <ToolGuidancePanel />
    <SovereignMigrationInspectorCard />
  </div>
);

export const VerifySection = ({
  snapshot,
  t,
  actionId,
  diagnosticRun,
  diagnosticHistory,
  onDoctorAction,
  onConnectClick,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  actionId: string | null;
  diagnosticRun: MemoryCommandDiagnosticRun | null;
  diagnosticHistory: MemoryCommandDiagnosticHistoryItem[];
  onDoctorAction: (action: DoctorExecutableAction) => void;
  onConnectClick?: () => void;
}) => (
  <div className="grid gap-4 xl:grid-cols-2">
    <Panel title={t('commandCenter.runtimeTitle')}>
      <RuntimePanel snapshot={snapshot} t={t} />
    </Panel>
    <Panel title={t('commandCenter.costTitle')}>
      <CostPanel snapshot={snapshot} t={t} />
    </Panel>
    <Panel title={t('commandCenter.replayTitle')} className="xl:col-span-2">
      {snapshot.replay.length ? (
        <div className="grid gap-2 md:grid-cols-2">
          {snapshot.replay.map((item) => (
            <ReplayRow key={item.chat_id} item={item} t={t} />
          ))}
        </div>
      ) : (
        <EmptyState label={t('commandCenter.replayEmpty')} />
      )}
    </Panel>
    <MemoryAdvancedVerifyPanels
      snapshot={snapshot}
      t={t}
      actionId={actionId}
      diagnosticRun={diagnosticRun}
      diagnosticHistory={diagnosticHistory}
      onDoctorAction={onDoctorAction}
      onConnectClick={onConnectClick}
    />
  </div>
);
