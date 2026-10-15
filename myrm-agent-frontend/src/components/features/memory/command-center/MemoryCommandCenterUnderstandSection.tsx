'use client';

/**
 * [INPUT]
 * ./MemoryEconomicsPanel::MemoryEconomicsPanel (POS: 记忆经济学面板)
 * ../cards/ConflictResolutionCard::ConflictResolutionCard (POS: 记忆冲突处置卡片)
 *
 * [OUTPUT]
 * UnderstandSection: the understand tab content.
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
import { CodeGraphAssetCard } from './CodeGraphAssetCard';
import { GraphRRFRetrievalCard } from './GraphRRFRetrievalCard';
import { HindsightReflectionCard } from './HindsightReflectionCard';
import { CodeMemoryCompactionCard } from './CodeMemoryCompactionCard';
import { GeneEvolutionInspectorCard } from './GeneEvolutionInspectorCard';
import { AutoRecallGovernanceCard } from './AutoRecallGovernanceCard';
import { GroundTruthDriftDefenseCard } from './GroundTruthDriftDefenseCard';
import { CrossAgentConflictArbitrationCard } from './CrossAgentConflictArbitrationCard';
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
    {/* Stateful Long-Horizon Memory Economics Profiler (Omri et al. 2026) */}
    <MemoryEconomicsPanel initialDashboard={snapshot.economics} />

    {/* Deterministic Behavioral Routine Metrics Panel (Zero Model Cost) */}
    <BehavioralMetricsPanel t={t} />

    {/* Repository History Evidence Digest Card */}
    <RepoEvidenceCard />

    {/* CodeGraph Memory Asset & Pre-Modification Impact Analysis Card */}
    <CodeGraphAssetCard />

    {/* Hybrid Vector and Knowledge Graph Reciprocal Rank Fusion Memory Card */}
    <GraphRRFRetrievalCard />

    {/* Hindsight Experience Replay and Retrospective Reflection Buffer Card */}
    <HindsightReflectionCard />

    {/* Token-Budget-Aware Codebase Semantic Memory Compaction Card */}
    <CodeMemoryCompactionCard />

    {/* Causal Experience Gene Synthesizer and Confidence Evolution Ledger Card */}
    <GeneEvolutionInspectorCard />

    {/* Targeted Experience Auto-Recall Trigger and 5-Turn Sliding Dedup Gate Card */}
    <AutoRecallGovernanceCard />

    {/* Ground Truth Priority & Code Drift Stale Memory Defense Card */}
    <GroundTruthDriftDefenseCard />

    {/* Cross-Agent Composable Context & Conflict Arbitration Engine Suite Card */}
    <CrossAgentConflictArbitrationCard />

    {/* Knowledge Graph Pre-Extraction Content Screening & Prompt Injection Shield Card */}
    <KnowledgeGraphPoisoningShieldCard />

    {/* Integration Disconnect Retained Context Purge & Provenance Revocation Shield Card (Item 179) */}
    <IntegrationRetainedContextPurgeCard />

    {/* Project State Living Fact Ledger & 4-Tier Context Projection Card (Item 63) */}
    <ProjectLivingFactLedgerCard />

    {/* First Encounter Onboarding Insight Sampling & Report Card (Item 67) */}
    <FirstEncounterReportCard />

    {/* Transparent Inspectable Model Private Notebook Suite Card (Item 89 P0) */}
    <PrivateNotebookCard />

    {/* Four-Tier Persistent Memory & FTS5 Self-Maintenance Compaction Card (Item 92 P0) */}
    <FourTierPersistentMemoryCard />

    {/* Temporal Knowledge Graph Decay & Entity Fact Conflict Resolution Card (Item 93 P0) */}
    <TemporalKnowledgeGraphCard />

    {/* Conversation Lineage Dedup & Automation Demotion Suite Card (Item 97 P0) */}
    <ConversationLineageDefenseCard />

    {/* Prompt-Cache Preserving Ephemeral Delta Memory Suite Card (Item 98 P0) */}
    <PromptCachePreservingDeltaCard defaultChatId={defaultChatId} />

    {isMemoryLabsEnabled() ? <TwoLayerDialecticStudioCard /> : null}

    {/* Budget Greedy Marginal Value Recall Packing Studio Card (Item 122 P2) */}
    <BudgetGreedyPackingStudioCard />

    {/* Memory Cube Scoped Isolation & Dynamic Mounting Studio Card (Item 124 P0) */}
    <MemoryCubeStudioCard />

    {/* Incremental Sliding Window Markdown Chunker Studio Card (Item 132 P1) */}
    <MarkdownChunkerStudioCard />

    {/* Multi-Platform Memory Migration & Import Engine Studio Card (Item 134 P1) */}
    <MultiPlatformMemoryMigrationStudioCard />

    {/* Retrieval Score Honesty & Raw vs Ranking Inspection Card (Item 142 P1) */}
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
