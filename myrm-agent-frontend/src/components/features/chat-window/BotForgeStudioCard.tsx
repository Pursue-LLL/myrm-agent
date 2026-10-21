import React, { useState } from 'react';
import {
  BotProfile,
  DEFAULT_CATALOG,
  DEFAULT_EXECUTION_STATE,
  OverlapCheckResult,
  PipelineExecutionState,
  TeamComposition,
} from './bot-forge/types';
import { ForgeHeaderView } from './bot-forge/ForgeHeaderView';
import { AgentForgeFormView } from './bot-forge/AgentForgeFormView';
import { TeamSquadForgeView } from './bot-forge/TeamSquadForgeView';
import { CatalogAndRollbackView } from './bot-forge/CatalogAndRollbackView';

export interface BotForgeStudioCardProps {
  chatId: string;
  initialCatalog?: BotProfile[];
  initialExecutionState?: PipelineExecutionState;
  onCheckOverlap?: (name: string, purpose: string) => Promise<OverlapCheckResult>;
  onCreateAgent?: (spec: BotProfile, isSandbox: boolean, allowOverlap: boolean) => Promise<PipelineExecutionState>;
  onCreateTeam?: (teamSpec: TeamComposition, isSandbox: boolean, allowOverlap: boolean) => Promise<PipelineExecutionState>;
  onCloneAgent?: (sourceName: string, targetName: string, newDisplayName?: string) => Promise<PipelineExecutionState>;
  onDeleteAgent?: (name: string) => Promise<boolean>;
}

export const BotForgeStudioCard: React.FC<BotForgeStudioCardProps> = ({
  chatId,
  initialCatalog = DEFAULT_CATALOG,
  initialExecutionState = DEFAULT_EXECUTION_STATE,
  onCheckOverlap,
  onCreateAgent,
  onCreateTeam,
  onCloneAgent,
  onDeleteAgent,
}) => {
  const [activeTab, setActiveTab] = useState<'agent' | 'team' | 'catalog' | 'pipeline'>('agent');
  const [catalog, setCatalog] = useState<BotProfile[]>(initialCatalog);
  const [latestState, setLatestState] = useState<PipelineExecutionState | null>(initialExecutionState);
  const [statusMessage, setStatusMessage] = useState<string>('Ready to forge agents & teams with builder safety bounds.');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const handleCheckOverlap = async (name: string, purpose: string): Promise<OverlapCheckResult> => {
    if (onCheckOverlap) {
      return onCheckOverlap(name, purpose);
    }
    // Default local simulation
    const normalized = name.toLowerCase().replace(/[\s_]+/g, '-');
    const duplicate = catalog.find((b) => b.name === normalized);
    if (duplicate) {
      return {
        verdict: 'duplicate_name',
        conflicting_name: duplicate.name,
        recommendation: `Agent '${duplicate.name}' exists. Suggest using '${normalized}-specialist'.`,
      };
    }
    return { verdict: 'unique' };
  };

  const handleCreateAgent = async (spec: BotProfile, isSandbox: boolean, allowOverlap: boolean): Promise<void> => {
    setIsProcessing(true);
    setStatusMessage(`Running deterministic creation pipeline for '${spec.name}'...`);
    try {
      if (onCreateAgent) {
        const result = await onCreateAgent(spec, isSandbox, allowOverlap);
        setLatestState(result);
        if (result.current_stage === 'completed') {
          setCatalog((prev) => [spec, ...prev.filter((b) => b.name !== spec.name)]);
          setStatusMessage(`Agent '${spec.name}' created & verified successfully.`);
          setActiveTab('catalog');
        } else {
          setStatusMessage(`Agent '${spec.name}' rolled back: ${result.error || 'Readiness checks blocked'}`);
          setActiveTab('pipeline');
        }
      } else {
        // Mock success fallback
        const mockState: PipelineExecutionState = {
          pipeline_id: `pipe-${Date.now().toString().slice(-6)}`,
          target_name: spec.name,
          is_team: false,
          current_stage: 'completed',
          created_agents: [spec.name],
          started_at: Date.now() - 500,
          completed_at: Date.now(),
          verification: {
            passed: true,
            severity: 'pass',
            findings: [],
            observed_state: {
              status: 'ready',
              model_ready: 'true',
              tools_bound: String(spec.tools.length),
              skills_bound: String(spec.skills.length),
            },
          },
        };
        setLatestState(mockState);
        setCatalog((prev) => [spec, ...prev.filter((b) => b.name !== spec.name)]);
        setStatusMessage(`Agent '${spec.name}' created & verified successfully.`);
        setActiveTab('catalog');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Builder Safety Violation: ${msg}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCreateTeam = async (
    teamSpec: TeamComposition,
    isSandbox: boolean,
    allowOverlap: boolean
  ): Promise<void> => {
    setIsProcessing(true);
    setStatusMessage(`Running transactional squad pipeline for '${teamSpec.team_name}'...`);
    try {
      if (onCreateTeam) {
        const result = await onCreateTeam(teamSpec, isSandbox, allowOverlap);
        setLatestState(result);
        if (result.current_stage === 'completed') {
          const allNew = [teamSpec.lead, ...teamSpec.specialists];
          setCatalog((prev) => [...allNew, ...prev]);
          setStatusMessage(`Squad '${teamSpec.team_name}' verified and provisioned (${allNew.length} agents).`);
          setActiveTab('catalog');
        } else {
          setStatusMessage(`Squad '${teamSpec.team_name}' failed & rolled back: ${result.error}`);
          setActiveTab('pipeline');
        }
      } else {
        const allNew = [teamSpec.lead, ...teamSpec.specialists];
        const mockState: PipelineExecutionState = {
          pipeline_id: `pipe-${Date.now().toString().slice(-6)}`,
          target_name: teamSpec.team_name,
          is_team: true,
          current_stage: 'completed',
          created_agents: allNew.map((a) => a.name),
          started_at: Date.now() - 1000,
          completed_at: Date.now(),
          verification: {
            passed: true,
            severity: 'pass',
            findings: [],
            observed_state: {
              squad_size: String(allNew.length),
              lead: teamSpec.lead.name,
            },
          },
        };
        setLatestState(mockState);
        setCatalog((prev) => [...allNew, ...prev]);
        setStatusMessage(`Squad '${teamSpec.team_name}' verified and provisioned (${allNew.length} agents).`);
        setActiveTab('catalog');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Builder Safety Violation: ${msg}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCloneAgent = async (sourceName: string, targetName: string, newDisplayName?: string): Promise<void> => {
    setIsProcessing(true);
    setStatusMessage(`Cloning '${sourceName}' -> '${targetName}' with prompt sanitization...`);
    try {
      if (onCloneAgent) {
        const result = await onCloneAgent(sourceName, targetName, newDisplayName);
        setLatestState(result);
        if (result.current_stage === 'completed') {
          const source = catalog.find((b) => b.name === sourceName);
          if (source) {
            const cloned: BotProfile = {
              ...source,
              name: targetName,
              display_name: newDisplayName || `${targetName.toUpperCase()}`,
            };
            setCatalog((prev) => [cloned, ...prev]);
          }
          setStatusMessage(`Agent '${targetName}' successfully cloned from '${sourceName}'.`);
          setActiveTab('catalog');
        } else {
          setStatusMessage(`Clone '${targetName}' rolled back: ${result.error}`);
          setActiveTab('pipeline');
        }
      } else {
        const source = catalog.find((b) => b.name === sourceName);
        if (source) {
          const cloned: BotProfile = {
            ...source,
            name: targetName,
            display_name: newDisplayName || `${targetName.toUpperCase()}`,
          };
          setCatalog((prev) => [cloned, ...prev]);
          setStatusMessage(`Agent '${targetName}' successfully cloned from '${sourceName}'.`);
          setActiveTab('catalog');
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Clone failed: ${msg}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeleteAgent = async (agentName: string): Promise<void> => {
    setIsProcessing(true);
    setStatusMessage(`Deleting agent '${agentName}' from session catalog...`);
    try {
      if (onDeleteAgent) {
        await onDeleteAgent(agentName);
      }
      setCatalog((prev) => prev.filter((b) => b.name !== agentName));
      setStatusMessage(`Agent '${agentName}' deleted successfully.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatusMessage(`Delete failed: ${msg}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <article
      aria-label="Bot Forge Studio Card"
      data-chat-id={chatId}
      className="flex flex-col gap-4 rounded-xl border border-border/70 bg-card/95 p-4 sm:p-5 shadow-sm text-foreground"
    >
      <ForgeHeaderView
        activeTab={activeTab}
        onTabChange={setActiveTab}
        totalAgents={catalog.length}
        isProcessing={isProcessing}
      />

      {/* Accessible Live Output region */}
      <output
        aria-live="polite"
        className="rounded-md border border-border/40 bg-muted/40 px-3 py-1.5 text-xs font-mono text-muted-foreground flex items-center gap-2"
      >
        <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
        <span>{statusMessage}</span>
      </output>

      {/* Tab Panels */}
      {activeTab === 'agent' && (
        <AgentForgeFormView
          isProcessing={isProcessing}
          onCheckOverlap={handleCheckOverlap}
          onCreateAgent={handleCreateAgent}
        />
      )}

      {activeTab === 'team' && (
        <TeamSquadForgeView
          isProcessing={isProcessing}
          onCreateTeam={handleCreateTeam}
        />
      )}

      {(activeTab === 'catalog' || activeTab === 'pipeline') && (
        <CatalogAndRollbackView
          catalog={catalog}
          latestState={latestState}
          isProcessing={isProcessing}
          onDeleteAgent={handleDeleteAgent}
          onCloneAgent={handleCloneAgent}
        />
      )}
    </article>
  );
};
