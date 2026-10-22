import React, { useId, useState } from 'react';
import {
  ConsensusVerdictItem,
  CouncilOfAgentsDeliberationCardProps,
  CouncilProposalItem,
  CritiquePointItem,
  DeliberationPhase,
  INITIAL_COUNCIL_SESSION,
} from './council/types';

const PHASE_SEQUENCE: DeliberationPhase[] = [
  'blind_proposal',
  'cross_critique',
  'rebuttal',
  'consensus_synthesis',
  'finalized',
];

const PHASE_LABELS: Record<DeliberationPhase, string> = {
  blind_proposal: '1. Blind Proposal',
  cross_critique: '2. Cross Critique',
  rebuttal: '3. Rebuttal & Defense',
  consensus_synthesis: '4. Consensus Synthesis',
  finalized: '5. Finalized',
};

export const CouncilOfAgentsDeliberationCard: React.FC<CouncilOfAgentsDeliberationCardProps> = ({
  sessionId,
  initialSession = INITIAL_COUNCIL_SESSION,
  onDismiss,
  onPhaseAdvanced,
  onConsensusReached,
}) => {
  const [session, setSession] = useState(initialSession);
  const [selectedProposalId, setSelectedProposalId] = useState<string>('prop-claude');
  const [activeCritiqueId, setActiveCritiqueId] = useState<string | null>(null);
  const [rebuttalInput, setRebuttalInput] = useState<string>('');

  const rebuttalInputId = useId();

  const proposalsList = Object.values(session.proposals);
  const activeProposal: CouncilProposalItem =
    session.proposals[selectedProposalId] ?? proposalsList[0];

  const handleAdvancePhase = () => {
    const currentIdx = PHASE_SEQUENCE.indexOf(session.phase);
    if (currentIdx < PHASE_SEQUENCE.length - 1) {
      const nextPhase = PHASE_SEQUENCE[currentIdx + 1];
      let synthesizedVerdict: ConsensusVerdictItem | null = session.consensus ?? null;

      if (nextPhase === 'consensus_synthesis' || nextPhase === 'finalized') {
        synthesizedVerdict = {
          verdictId: `verdict-${Date.now().toString(36)}`,
          finalDecision: `Adopt Hybrid Tier Architecture: Stateless edge routing combined with scoped actor workers. Synthesized across ${proposalsList.length} heterogeneous models.`,
          confidenceRating: 0.92,
          keyTradeoffs: [
            'Adopted primary compromise from DeepSeek-R1 and Claude-3.5-Sonnet.',
            'Quorum-fenced actors for high-contention writes; redis-backed stateless routes for queries.',
            'Cluster blast radius reduced by 70% compared to pure stateful mesh.',
          ],
          participatingModels: proposalsList.map((p) => p.modelName),
          dissentingOpinions: [
            'GPT-4o raised concerns on operational complexity of dual-runtime deployment.',
          ],
        };
        onConsensusReached?.(synthesizedVerdict);
      }

      setSession((prev) => ({
        ...prev,
        phase: nextPhase,
        consensus: synthesizedVerdict,
        updatedAt: Date.now(),
      }));

      onPhaseAdvanced?.(nextPhase);
    }
  };

  const handleSubmitRebuttal = (critiqueId: string) => {
    if (!rebuttalInput.trim()) {
      return;
    }
    setSession((prev) => ({
      ...prev,
      critiques: prev.critiques.map((c) =>
        c.critiqueId === critiqueId ? { ...c, defenseRebuttal: rebuttalInput.trim() } : c,
      ),
      updatedAt: Date.now(),
    }));
    setRebuttalInput('');
    setActiveCritiqueId(null);
  };

  return (
    <section
      aria-label="Council of Agents Multi-Model Deliberation Protocol"
      className="p-4 bg-slate-900/90 border border-slate-700/80 rounded-xl shadow-xl text-slate-100 flex flex-col gap-4 text-xs font-sans"
    >
      <header className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-indigo-400 ring-4 ring-indigo-500/20" />
          <h2 className="font-semibold text-sm text-slate-100 tracking-wide">
            Council of Agents Deliberation
          </h2>
          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            Session: {sessionId ?? session.sessionId}
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close council deliberation card"
            className="text-slate-400 hover:text-slate-200 transition-colors p-1"
          >
            ✕
          </button>
        )}
      </header>

      {/* Topic Title */}
      <div className="bg-slate-800/40 border border-slate-700/50 p-2.5 rounded-lg flex flex-col gap-1">
        <span className="text-[10px] uppercase font-mono tracking-wider text-slate-400">
          Deliberation Topic
        </span>
        <p className="text-slate-200 font-medium text-xs">{session.deliberationTopic}</p>
      </div>

      {/* 5-Phase Step Sequence */}
      <nav aria-label="Deliberation Phases" className="flex items-center gap-1 overflow-x-auto pb-1">
        {PHASE_SEQUENCE.map((phase) => {
          const isCurrent = session.phase === phase;
          const isDone =
            PHASE_SEQUENCE.indexOf(session.phase) > PHASE_SEQUENCE.indexOf(phase);
          return (
            <span
              key={phase}
              className={`px-2 py-1 rounded text-[10px] font-medium whitespace-nowrap transition-colors border ${
                isCurrent
                  ? 'bg-indigo-600/30 text-indigo-300 border-indigo-500/80 shadow-sm'
                  : isDone
                  ? 'bg-slate-800/80 text-emerald-400 border-emerald-500/40'
                  : 'bg-slate-800/40 text-slate-500 border-slate-800'
              }`}
            >
              {isDone ? '✔ ' : ''}
              {PHASE_LABELS[phase]}
            </span>
          );
        })}
      </nav>

      {/* Multi-Model Proposal Cards */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="font-medium text-slate-300 text-xs">
            Model Blind Proposals ({proposalsList.length})
          </span>
          <span className="text-[10px] text-slate-400">Heterogeneous Blind Review</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {proposalsList.map((p) => {
            const isSelected = p.proposalId === selectedProposalId;
            return (
              <button
                key={p.proposalId}
                type="button"
                onClick={() => setSelectedProposalId(p.proposalId)}
                className={`p-2.5 text-left rounded-lg border transition-all ${
                  isSelected
                    ? 'border-indigo-500/90 bg-indigo-950/40 shadow-sm shadow-indigo-500/10'
                    : 'border-slate-800 bg-slate-800/40 hover:border-slate-700 hover:bg-slate-800/80'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-slate-200 truncate">{p.modelName}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-700/70 text-slate-300">
                    {Math.round(p.confidenceScore * 100)}% Conf
                  </span>
                </div>
                <p className="text-[11px] text-slate-300 line-clamp-2">{p.title}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Proposal Detail View */}
      {activeProposal && (
        <div className="p-3 bg-slate-800/60 border border-slate-700/60 rounded-lg flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-100 text-xs">
              {activeProposal.modelName}: {activeProposal.title}
            </h3>
            <span className="text-[10px] text-indigo-300 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-800/60">
              Confidence Score: {activeProposal.confidenceScore}
            </span>
          </div>

          <div className="flex flex-col gap-1 text-[11px] text-slate-300">
            <span className="text-slate-400 font-medium">Reasoning Trajectory:</span>
            <ul className="list-disc list-inside space-y-0.5 pl-1 text-slate-300">
              {activeProposal.reasoningSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>

          <div className="flex flex-wrap gap-1 items-center pt-1">
            <span className="text-slate-400">Core Pillars:</span>
            {activeProposal.keyArguments.map((arg) => (
              <span
                key={arg}
                className="px-2 py-0.5 rounded bg-slate-700/60 text-[10px] text-slate-200 border border-slate-600/40"
              >
                {arg}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Cross Critique & Rebuttal Section */}
      <div className="p-3 bg-slate-800/40 border border-slate-700/60 rounded-lg flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-200 text-xs">Cross-Critique & Defense Rebuttals</h3>
          <span className="text-[10px] text-slate-400">{session.critiques.length} critiques logged</span>
        </div>

        <div className="flex flex-col gap-2">
          {session.critiques.map((c: CritiquePointItem) => (
            <div
              key={c.critiqueId}
              className="p-2 bg-slate-900/70 border border-slate-800 rounded flex flex-col gap-1 text-[11px]"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 font-mono text-[10px]">
                  <span className="text-purple-400">{c.sourceMemberId}</span>
                  <span className="text-slate-500">attacks</span>
                  <span className="text-indigo-400">{c.targetProposalId}</span>
                </div>
                <span
                  className={`text-[9px] uppercase px-1.5 py-0.2 rounded font-mono border ${
                    c.severity === 'blocker'
                      ? 'bg-red-950 text-red-300 border-red-700'
                      : c.severity === 'high'
                      ? 'bg-amber-950 text-amber-300 border-amber-700'
                      : 'bg-slate-800 text-slate-300 border-slate-700'
                  }`}
                >
                  {c.severity}
                </span>
              </div>

              <p className="text-slate-300">{c.critiquePoints.join(' ')}</p>

              {c.defenseRebuttal ? (
                <div className="text-[10px] bg-slate-950/80 p-1.5 rounded border border-slate-800 text-emerald-300 flex items-start gap-1">
                  <span className="text-emerald-500 font-bold">↳ Defense:</span>
                  <span>{c.defenseRebuttal}</span>
                </div>
              ) : (
                <div className="pt-1">
                  {activeCritiqueId === c.critiqueId ? (
                    <div className="flex flex-col gap-1.5">
                      <label htmlFor={rebuttalInputId} className="text-slate-400 text-[10px]">
                        Draft Defense Rebuttal:
                      </label>
                      <textarea
                        id={rebuttalInputId}
                        rows={2}
                        value={rebuttalInput}
                        onChange={(e) => setRebuttalInput(e.target.value)}
                        placeholder="Provide counter-evidence or mitigation..."
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleSubmitRebuttal(c.critiqueId)}
                          className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px] transition-colors"
                        >
                          Submit Rebuttal
                        </button>
                        <button
                          type="button"
                          onClick={() => setActiveCritiqueId(null)}
                          className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded text-[10px] transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveCritiqueId(c.critiqueId);
                        setRebuttalInput('');
                      }}
                      className="text-indigo-400 hover:text-indigo-300 text-[10px] underline"
                    >
                      + Add Defense Rebuttal
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Consensus Verdict Dashboard */}
      {session.consensus && (
        <output
          aria-live="polite"
          className="p-3 bg-gradient-to-br from-indigo-950/50 to-slate-900/80 border border-indigo-600/60 rounded-lg flex flex-col gap-2"
        >
          <div className="flex items-center justify-between">
            <span className="font-semibold text-indigo-300 text-xs">
              ✔ Consensus Verdict Reached
            </span>
            <span className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-600/70 text-emerald-300 text-[10px] font-mono">
              Confidence Rating: {session.consensus.confidenceRating * 100}%
            </span>
          </div>
          <p className="text-slate-100 font-medium text-xs leading-relaxed">
            {session.consensus.finalDecision}
          </p>

          <div className="flex flex-col gap-1 text-[11px] pt-1">
            <span className="text-slate-400 font-medium">Key Architectural Tradeoffs:</span>
            <ul className="list-disc list-inside space-y-0.5 text-slate-300">
              {session.consensus.keyTradeoffs.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </div>

          {session.consensus.dissentingOpinions.length > 0 && (
            <div className="text-[10px] text-amber-300/90 bg-amber-950/30 p-2 rounded border border-amber-800/40">
              <span className="font-semibold">Dissenting Opinions: </span>
              {session.consensus.dissentingOpinions.join('; ')}
            </div>
          )}
        </output>
      )}

      {/* Stage Progression Footer */}
      <footer className="flex items-center justify-between border-t border-slate-700/60 pt-3">
        <span className="text-[11px] text-slate-400">
          Current: <strong className="text-slate-200">{PHASE_LABELS[session.phase]}</strong>
        </span>
        <button
          type="button"
          onClick={handleAdvancePhase}
          disabled={session.phase === 'finalized'}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium rounded transition-colors text-xs"
        >
          {session.phase === 'rebuttal'
            ? 'Synthesize Consensus'
            : session.phase === 'finalized'
            ? 'Deliberation Finalized'
            : 'Advance to Next Phase →'}
        </button>
      </footer>
    </section>
  );
};
