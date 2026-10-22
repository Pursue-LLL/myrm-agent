import React, { useState } from 'react';
import { BotProfile, TeamComposition } from './types';

export interface TeamSquadForgeViewProps {
  isProcessing: boolean;
  onCreateTeam: (teamSpec: TeamComposition, isSandbox: boolean, allowOverlap: boolean) => Promise<void>;
}

export const TeamSquadForgeView: React.FC<TeamSquadForgeViewProps> = ({
  isProcessing,
  onCreateTeam,
}) => {
  const [teamName, setTeamName] = useState<string>('fullstack-engineering-squad');
  const [teamPurpose, setTeamPurpose] = useState<string>('Fullstack product delivery team with architecture, frontend, and backend specialists.');
  const [isSandbox, setIsSandbox] = useState<boolean>(false);
  const [allowOverlap, setAllowOverlap] = useState<boolean>(false);

  const [lead, setLead] = useState<BotProfile>({
    name: 'squad-architect',
    display_name: 'Squad Architect',
    description: 'Decomposes roadmap tickets, reviews pull requests, and orchestrates specialist task dispatch',
    system_prompt: 'You lead this engineering squad. Enforce architecture guidelines and delegate tasks.',
    model: 'gpt-5',
    tools: ['file_read', 'file_write', 'web_search'],
    skills: ['code_review', 'ast_lint'],
    mcp_servers: [],
    cron_routines: [],
    role_type: 'lead',
  });

  const [specialists, setSpecialists] = useState<BotProfile[]>([
    {
      name: 'frontend-coder',
      display_name: 'Frontend Coder',
      description: 'Implements accessible React components, Tailwind styling, and responsive UI states',
      system_prompt: 'You code frontend features in TypeScript/React with 0 type errors.',
      model: 'gpt-5',
      tools: ['file_read', 'file_write'],
      skills: ['code_review'],
      mcp_servers: [],
      cron_routines: [],
      role_type: 'specialist',
    },
    {
      name: 'backend-engineer',
      display_name: 'Backend Engineer',
      description: 'Designs FastAPI endpoints, Pydantic schemas, and SQLAlchemy data layer integrations',
      system_prompt: 'You code high-performance backend endpoints adhering strictly to PEP8.',
      model: 'claude-3-7-sonnet',
      tools: ['file_read', 'file_write', 'bash_exec'],
      skills: ['data_analysis'],
      mcp_servers: [],
      cron_routines: [],
      role_type: 'specialist',
    },
  ]);

  const handleAddSpecialist = () => {
    const nextIdx = specialists.length + 1;
    const newMember: BotProfile = {
      name: `specialist-${nextIdx}`,
      display_name: `Specialist ${nextIdx}`,
      description: `Domain specialist responsible for task track ${nextIdx}`,
      system_prompt: `You handle focused subsystem tasks with zero hallucination.`,
      model: 'gpt-5',
      tools: ['file_read', 'file_write'],
      skills: [],
      mcp_servers: [],
      cron_routines: [],
      role_type: 'specialist',
    };
    setSpecialists((prev) => [...prev, newMember]);
  };

  const handleRemoveSpecialist = (idx: number) => {
    setSpecialists((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const teamSpec: TeamComposition = {
      team_name: teamName.trim().toLowerCase(),
      team_purpose: teamPurpose.trim(),
      lead,
      specialists,
    };
    await onCreateTeam(teamSpec, isSandbox, allowOverlap);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-md bg-indigo-500/10 border border-indigo-500/20 p-3 text-xs text-indigo-400">
        <div className="font-semibold text-foreground flex items-center gap-1.5">
          <span>👥</span>
          <span>Transactional Squad Construction Pipeline</span>
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
          Create an authoritative Squad Lead along with synchronized Specialist agents. If any member fails pre-check verification, the entire squad is atomically rolled back without orphaned store artifacts.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="team-name-input" className="block text-xs font-medium text-foreground mb-1">
            Team Squad Name *
          </label>
          <input
            id="team-name-input"
            type="text"
            required
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring font-mono"
          />
        </div>

        <div>
          <label htmlFor="team-purpose-input" className="block text-xs font-medium text-foreground mb-1">
            Squad Mission / Purpose *
          </label>
          <input
            id="team-purpose-input"
            type="text"
            required
            value={teamPurpose}
            onChange={(e) => setTeamPurpose(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      </div>

      {/* Squad Lead Card */}
      <div className="rounded-lg border border-border/50 bg-muted/20 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
            <span className="rounded bg-indigo-500/20 text-indigo-400 px-1.5 py-0.5 text-[10px] font-mono">
              LEAD
            </span>
            <span>Squad Lead: {lead.display_name}</span>
          </span>
          <span className="text-[11px] font-mono text-muted-foreground">{lead.model}</span>
        </div>
        <p className="text-xs text-muted-foreground">{lead.description}</p>
        <div className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground">
          <span>Tools: {lead.tools.join(', ')}</span>
        </div>
      </div>

      {/* Specialists Section */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-foreground">
            Specialists ({specialists.length})
          </span>
          <button
            type="button"
            onClick={handleAddSpecialist}
            className="text-xs text-indigo-500 hover:text-indigo-400 font-medium underline"
          >
            + Add Specialist
          </button>
        </div>

        <div className="space-y-2">
          {specialists.map((spec, idx) => (
            <div
              key={spec.name}
              className="flex items-start justify-between rounded-lg border border-border/40 bg-card p-2.5 text-xs"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{spec.display_name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">({spec.name})</span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                    {spec.model}
                  </span>
                </div>
                <p className="text-muted-foreground text-[11px]">{spec.description}</p>
                <div className="text-[10px] font-mono text-muted-foreground">
                  Tools: {spec.tools.join(', ') || 'None'}
                </div>
              </div>

              {specialists.length > 1 && (
                <button
                  type="button"
                  onClick={() => handleRemoveSpecialist(idx)}
                  className="text-xs text-destructive hover:opacity-80 px-1"
                  title="Remove specialist"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-md border border-border/40 bg-muted/10 p-2 text-xs">
        <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer text-[11px]">
          <input
            type="checkbox"
            checked={isSandbox}
            onChange={(e) => setIsSandbox(e.target.checked)}
            className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
          />
          <span>Execute squad in isolated sandbox</span>
        </label>

        <label className="flex items-center gap-1.5 text-muted-foreground cursor-pointer text-[11px]">
          <input
            type="checkbox"
            checked={allowOverlap}
            onChange={(e) => setAllowOverlap(e.target.checked)}
            className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
          />
          <span>Bypass duty overlap warnings</span>
        </label>
      </div>

      <button
        type="submit"
        disabled={isProcessing}
        className="w-full rounded-md bg-primary py-2 px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-sm"
      >
        {isProcessing ? 'Verifying & Materializing Squad Pipeline...' : 'Deploy Squad with Atomic Rollback Guard'}
      </button>
    </form>
  );
};
