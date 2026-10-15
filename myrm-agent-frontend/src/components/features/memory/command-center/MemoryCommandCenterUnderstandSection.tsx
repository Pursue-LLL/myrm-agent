'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandCenterResponse (POS: Frontend Personal Brain Command Center client)
 * @/lib/memory/memoryLabs::isMemoryLabsEnabled (POS: Memory Command Center 与设置内实验面板的开关)
 * ./MemoryEconomicsPanel::MemoryEconomicsPanel (POS: 前端记忆命令中心经济学剖析组件)
 * ../insights/BehavioralMetricsPanel::BehavioralMetricsPanel (POS: 记忆指挥中心行为洞察面板)
 * ../cards/ConflictResolutionCard::ConflictResolutionCard (POS: 记忆冲突仲裁卡片组件)
 * ./MemoryCommandCenterObservationPanels::InfluenceRow (POS: 个人大脑指挥中心的只读观测面板)
 *
 * [OUTPUT]
 * UnderstandSection: 「理解」分区内容，按序挂载经济学、行为指标与各记忆能力卡片，末尾为影响与冲突两栏。
 *
 * [POS]
 * 个人大脑指挥中心「理解」分区：记忆经济学、行为指标、各记忆能力卡片以及影响与冲突面板。
 */

import { isMemoryLabsEnabled } from '@/lib/memory/memoryLabs';
import type { MemoryCommandCenterResponse } from '@/services/memory/commandCenter';
import { ConflictResolutionCard } from '../cards/ConflictResolutionCard';
import { BehavioralMetricsPanel } from '../insights/BehavioralMetricsPanel';
import { RepoEvidenceCard } from '../cards/RepoEvidenceCard';
import { MemoryEconomicsPanel } from './MemoryEconomicsPanel';
import { GraphRRFRetrievalCard } from './GraphRRFRetrievalCard';
import { HindsightReflectionCard } from './HindsightReflectionCard';
import { GroundTruthDriftDefenseCard } from './GroundTruthDriftDefenseCard';
import { KnowledgeGraphPoisoningShieldCard } from './KnowledgeGraphPoisoningShieldCard';
import { IntegrationRetainedContextPurgeCard } from './IntegrationRetainedContextPurgeCard';
import { ProjectLivingFactLedgerCard } from './ProjectLivingFactLedgerCard';
import { FirstEncounterReportCard } from './FirstEncounterReportCard';
import { PrivateNotebookCard } from './PrivateNotebookCard';
import { FourTierPersistentMemoryCard } from './FourTierPersistentMemoryCard';
import { TemporalKnowledgeGraphCard } from './TemporalKnowledgeGraphCard';
import { ConversationLineageDefenseCard } from './ConversationLineageDefenseCard';
import { PromptCachePreservingDeltaCard } from './PromptCachePreservingDeltaCard';
import { TwoLayerDialecticStudioCard } from './TwoLayerDialecticStudioCard';
import { BudgetGreedyPackingStudioCard } from './BudgetGreedyPackingStudioCard';
import { MemoryCubeStudioCard } from './MemoryCubeStudioCard';
import { MarkdownChunkerStudioCard } from './MarkdownChunkerStudioCard';
import { MultiPlatformMemoryMigrationStudioCard } from './MultiPlatformMemoryMigrationStudioCard';
import { ScoreHonestyInspectionCard } from './ScoreHonestyInspectionCard';
import type { MemoryTranslation } from './memoryCommandCenterFormat';
import { Panel, EmptyState } from './MemoryCommandCenterPrimitives';
import { InfluenceRow } from './MemoryCommandCenterObservationPanels';

export const UnderstandSection = ({
  snapshot,
  t,
  onResolveConflict,
  actionId,
  defaultChatId,
}: {
  snapshot: MemoryCommandCenterResponse;
  t: MemoryTranslation;
  onResolveConflict?: (conflictId: string, action: 'keep_new' | 'keep_old' | 'coexist') => Promise<void>;
  actionId?: string | null;
  defaultChatId?: string | null;
}) => (
  <div className="space-y-4">
    <MemoryEconomicsPanel initialDashboard={snapshot.economics} />
    <BehavioralMetricsPanel t={t} />
    <RepoEvidenceCard />
    <GraphRRFRetrievalCard />
    <HindsightReflectionCard />
    <GroundTruthDriftDefenseCard />
    <KnowledgeGraphPoisoningShieldCard />
    <IntegrationRetainedContextPurgeCard />
    <ProjectLivingFactLedgerCard />
    <FirstEncounterReportCard />
    <PrivateNotebookCard />
    <FourTierPersistentMemoryCard />
    <TemporalKnowledgeGraphCard />
    <ConversationLineageDefenseCard />
    <PromptCachePreservingDeltaCard defaultChatId={defaultChatId} />
    {isMemoryLabsEnabled() ? <TwoLayerDialecticStudioCard /> : null}
    <BudgetGreedyPackingStudioCard />
    <MemoryCubeStudioCard />
    <MarkdownChunkerStudioCard />
    <MultiPlatformMemoryMigrationStudioCard />
    <ScoreHonestyInspectionCard />
    <div className="grid gap-4 xl:grid-cols-2">
      <Panel title={t('commandCenter.influenceTitle')}>
        {snapshot.influence.length ? (
          <div className="space-y-2">
            {snapshot.influence.map((item) => (
              <InfluenceRow key={item.id} item={item} t={t} />
            ))}
          </div>
        ) : (
          <EmptyState label={t('commandCenter.influenceEmpty')} />
        )}
      </Panel>
      <Panel title={t('commandCenter.conflictsTitle')}>
        {snapshot.conflicts.length ? (
          <div className="space-y-3">
            {snapshot.conflicts.map((item) => (
              <ConflictResolutionCard
                key={item.id}
                item={item}
                onResolve={onResolveConflict}
                resolving={Boolean(actionId?.startsWith(`conflict:${item.id}`))}
              />
            ))}
          </div>
        ) : (
          <EmptyState label={t('commandCenter.conflictsEmpty')} />
        )}
      </Panel>
    </div>
  </div>
);
