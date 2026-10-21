import React, { useState } from 'react';
import { CardPriority, KANBAN_LANES, KanbanCard, KanbanLane } from './types';

export interface CardDetailDrawerProps {
  card: KanbanCard | null;
  allCards: Record<string, KanbanCard>;
  onClose: () => void;
  onTransition: (cardId: string, lane: KanbanLane) => void;
  onHumanOverride: (
    cardId: string,
    agent?: string,
    priority?: CardPriority,
    lane?: KanbanLane,
  ) => void;
  onMountArtifact: (
    cardId: string,
    name: string,
    artifactType: string,
    filePath?: string,
    preview?: string,
  ) => void;
}

export const CardDetailDrawer: React.FC<CardDetailDrawerProps> = ({
  card,
  allCards,
  onClose,
  onTransition,
  onHumanOverride,
  onMountArtifact,
}) => {
  const [selectedLane, setSelectedLane] = useState<KanbanLane | null>(null);
  const [selectedPriority, setSelectedPriority] = useState<CardPriority | null>(null);
  const [agentInput, setAgentInput] = useState<string>('');
  const [artifactName, setArtifactName] = useState<string>('');
  const [artifactType, setArtifactType] = useState<string>('diff');
  const [artifactPath, setArtifactPath] = useState<string>('');
  const [artifactContent, setArtifactContent] = useState<string>('');
  const [showArtifactForm, setShowArtifactForm] = useState<boolean>(false);

  if (!card) {
    return null;
  }

  const currentLane = selectedLane || card.lane;
  const currentPriority = selectedPriority || card.priority;
  const currentAgent = agentInput || card.assigned_agent;

  const handleSaveOverride = (e: React.FormEvent) => {
    e.preventDefault();
    onHumanOverride(card.card_id, currentAgent, currentPriority, currentLane);
  };

  const handleAddArtifactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!artifactName.trim()) {
      return;
    }
    onMountArtifact(
      card.card_id,
      artifactName.trim(),
      artifactType,
      artifactPath.trim() ? artifactPath.trim() : undefined,
      artifactContent.trim() ? artifactContent.trim() : undefined,
    );
    setArtifactName('');
    setArtifactPath('');
    setArtifactContent('');
    setShowArtifactForm(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-background/60 backdrop-blur-xs">
      <dialog
        open
        className="w-full max-w-lg h-full overflow-y-auto border-l border-border bg-card p-6 shadow-xl flex flex-col justify-between m-0"
        aria-label="Card Detail Drawer"
      >
        <div className="space-y-6">
          <div className="flex items-start justify-between border-b border-border/40 pb-3">
            <div>
              <span className="text-[11px] font-mono text-muted-foreground uppercase tracking-wider">
                Task Card • {card.card_id}
              </span>
              <h3 className="text-base font-bold text-foreground mt-0.5">
                {card.title}
              </h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              aria-label="Close Drawer"
            >
              ✕
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label htmlFor="drawer-card-desc" className="block text-xs font-semibold text-muted-foreground mb-1">
                Description & Mission Scope
              </label>
              <p id="drawer-card-desc" className="text-xs text-foreground bg-muted/30 p-2.5 rounded-md border border-border/40 leading-relaxed">
                {card.description || 'No description provided.'}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="block text-xs font-semibold text-muted-foreground mb-1">
                  Card Sandbox Scope
                </span>
                <span className="inline-block rounded bg-muted/60 px-2 py-1 text-xs font-mono text-foreground border border-border/30">
                  {card.sandbox_subdir}
                </span>
              </div>
              <div>
                <span className="block text-xs font-semibold text-muted-foreground mb-1">
                  Status
                </span>
                <span className="inline-block rounded bg-indigo-500/10 text-indigo-500 px-2 py-1 text-xs font-semibold border border-indigo-500/20 uppercase">
                  {card.lane}
                </span>
              </div>
            </div>

            {/* Human in the loop override form */}
            <form onSubmit={handleSaveOverride} className="rounded-lg border border-border/50 bg-muted/20 p-3.5 space-y-3">
              <span className="text-xs font-bold text-foreground block">
                Human-in-the-Loop Override & Reassignment
              </span>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="drawer-lane-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
                    Swimlane Column
                  </label>
                  <select
                    id="drawer-lane-select"
                    value={currentLane}
                    onChange={(e) => setSelectedLane(e.target.value as KanbanLane)}
                    className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground"
                  >
                    {KANBAN_LANES.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="drawer-prio-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
                    Priority
                  </label>
                  <select
                    id="drawer-prio-select"
                    value={currentPriority}
                    onChange={(e) => setSelectedPriority(e.target.value as CardPriority)}
                    className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground"
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="drawer-agent-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                  Assigned Specialist Agent
                </label>
                <input
                  id="drawer-agent-input"
                  type="text"
                  value={currentAgent}
                  onChange={(e) => setAgentInput(e.target.value)}
                  placeholder="e.g. @backend-dev"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="submit"
                  className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
                >
                  Save Override
                </button>
              </div>
            </form>

            {/* Dependency DAG list */}
            <div>
              <span className="block text-xs font-semibold text-muted-foreground mb-1.5">
                Prerequisite DAG Dependencies
              </span>
              {card.depends_on.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">
                  No upstream dependencies. Card is independent.
                </p>
              ) : (
                <div className="space-y-1.5">
                  {card.depends_on.map((depId) => {
                    const depCard = allCards[depId];
                    const isDone = depCard?.lane === 'done';
                    return (
                      <div
                        key={depId}
                        className="flex items-center justify-between rounded-md border border-border/40 bg-muted/30 px-2.5 py-1.5 text-xs"
                      >
                        <span className="font-mono text-foreground font-medium">
                          {depCard ? depCard.title : depId}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            isDone
                              ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                              : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                          }`}
                        >
                          {isDone ? '✓ Completed' : 'Waiting'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Mounted Artifacts Section */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-muted-foreground">
                  Mounted Output Artifacts ({card.artifacts.length})
                </span>
                <button
                  type="button"
                  onClick={() => setShowArtifactForm(!showArtifactForm)}
                  className="text-xs text-primary hover:underline font-medium"
                >
                  {showArtifactForm ? 'Cancel' : '+ Mount Artifact'}
                </button>
              </div>

              {showArtifactForm && (
                <form
                  onSubmit={handleAddArtifactSubmit}
                  className="rounded-md border border-border/60 bg-muted/30 p-3 space-y-2.5 mb-3"
                >
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label htmlFor="art-name-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                        Artifact Title
                      </label>
                      <input
                        id="art-name-input"
                        type="text"
                        value={artifactName}
                        onChange={(e) => setArtifactName(e.target.value)}
                        placeholder="e.g. diff.patch"
                        className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
                        required
                      />
                    </div>
                    <div>
                      <label htmlFor="art-type-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
                        Artifact Type
                      </label>
                      <select
                        id="art-type-select"
                        value={artifactType}
                        onChange={(e) => setArtifactType(e.target.value)}
                        className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
                      >
                        <option value="diff">Diff</option>
                        <option value="file">File</option>
                        <option value="report">Report</option>
                        <option value="test_result">Test Result</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label htmlFor="art-path-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                      File Path (Optional)
                    </label>
                    <input
                      id="art-path-input"
                      type="text"
                      value={artifactPath}
                      onChange={(e) => setArtifactPath(e.target.value)}
                      placeholder="e.g. tasks/card-1/schema.json"
                      className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
                    />
                  </div>

                  <div>
                    <label htmlFor="art-preview-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
                      Content Preview (Optional)
                    </label>
                    <textarea
                      id="art-preview-input"
                      value={artifactContent}
                      onChange={(e) => setArtifactContent(e.target.value)}
                      placeholder="Paste diff snippet or report preview..."
                      rows={2}
                      className="w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground font-mono"
                    />
                  </div>

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors"
                    >
                      Attach Artifact
                    </button>
                  </div>
                </form>
              )}

              {card.artifacts.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">
                  No artifacts mounted to this card yet.
                </p>
              ) : (
                <div className="space-y-2">
                  {card.artifacts.map((art) => (
                    <div
                      key={art.artifact_id}
                      className="rounded-md border border-border/50 bg-background p-2.5 space-y-1.5 shadow-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs text-foreground">
                          {art.name}
                        </span>
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                          {art.artifact_type}
                        </span>
                      </div>
                      {art.file_path && (
                        <p className="text-[11px] font-mono text-muted-foreground">
                          path: {art.file_path}
                        </p>
                      )}
                      {art.content_preview && (
                        <pre className="rounded bg-zinc-950 p-2 font-mono text-[10px] text-zinc-300 overflow-x-auto max-h-24">
                          {art.content_preview}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="pt-4 border-t border-border/40 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
          >
            Close
          </button>
          {card.lane !== 'done' && (
            <button
              type="button"
              onClick={() => onTransition(card.card_id, 'done')}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 transition-colors"
            >
              Mark Card Done & Auto-Unblock
            </button>
          )}
        </div>
      </dialog>
    </div>
  );
};
