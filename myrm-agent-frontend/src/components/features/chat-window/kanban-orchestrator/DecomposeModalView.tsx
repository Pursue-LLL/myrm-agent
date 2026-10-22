import React, { useState } from 'react';

export interface DecomposeModalViewProps {
  isOpen: boolean;
  isProcessing: boolean;
  onClose: () => void;
  onDecompose: (goal: string, roster: string[]) => void;
}

export const DecomposeModalView: React.FC<DecomposeModalViewProps> = ({
  isOpen,
  isProcessing,
  onClose,
  onDecompose,
}) => {
  const [goal, setGoal] = useState<string>('Build real-time notification WebSocket channel');
  const [roster, setRoster] = useState<string>('@architect, @backend-dev, @frontend-dev, @tester');

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim() || isProcessing) {
      return;
    }
    const parsedRoster = roster
      .split(',')
      .map((r) => r.trim())
      .filter((r) => r.length > 0);
    onDecompose(goal.trim(), parsedRoster);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-xs p-4">
      <dialog
        open
        className="w-full max-w-md rounded-xl border border-border bg-card p-5 shadow-xl space-y-4 m-0"
        aria-label="Decompose Goal Dialog"
      >
        <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="text-base">⚡</span>
            <h3 className="text-sm font-bold text-foreground">
              Boss Agent Goal Auto-Decomposition
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">
          The Boss Agent will analyze your objective, construct sequenced task cards with prerequisite DAG dependency arrows, and allocate cards to specialist roles.
        </p>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label htmlFor="decompose-goal-input" className="block text-xs font-semibold text-muted-foreground mb-1">
              Project Objective / Mission
            </label>
            <textarea
              id="decompose-goal-input"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Describe the end-to-end mission to decompose..."
              rows={3}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:ring-1 focus:ring-primary"
              required
            />
          </div>

          <div>
            <label htmlFor="decompose-roster-input" className="block text-xs font-semibold text-muted-foreground mb-1">
              Available Specialist Roster
            </label>
            <input
              id="decompose-roster-input"
              type="text"
              value={roster}
              onChange={(e) => setRoster(e.target.value)}
              placeholder="@architect, @backend-dev, @tester"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/30">
            <button
              type="button"
              onClick={onClose}
              disabled={isProcessing}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isProcessing}
              className="rounded-md bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-xs disabled:opacity-50"
            >
              {isProcessing ? 'Decomposing...' : 'Decompose & Sequenced DAG'}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
};
