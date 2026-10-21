import React, { useState } from 'react';
import { CardPriority, CreateCardInput, KanbanCard } from './types';

export interface AddCardModalViewProps {
  isOpen: boolean;
  isProcessing: boolean;
  existingCards: Record<string, KanbanCard>;
  onClose: () => void;
  onCreateCard: (input: CreateCardInput) => void;
}

export const AddCardModalView: React.FC<AddCardModalViewProps> = ({
  isOpen,
  isProcessing,
  existingCards,
  onClose,
  onCreateCard,
}) => {
  const [title, setTitle] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [assignedAgent, setAssignedAgent] = useState<string>('@backend-dev');
  const [priority, setPriority] = useState<CardPriority>('medium');
  const [selectedDeps, setSelectedDeps] = useState<string[]>([]);

  if (!isOpen) {
    return null;
  }

  const handleToggleDep = (cardId: string) => {
    setSelectedDeps((prev) => {
      if (prev.includes(cardId)) {
        return prev.filter((id) => id !== cardId);
      }
      return [...prev, cardId];
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || isProcessing) {
      return;
    }
    onCreateCard({
      title: title.trim(),
      description: description.trim(),
      assigned_agent: assignedAgent.trim() || '@worker',
      depends_on: selectedDeps,
      priority,
    });
    setTitle('');
    setDescription('');
    setSelectedDeps([]);
  };

  const cardList = Object.values(existingCards);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-xs p-4">
      <dialog
        open
        className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto m-0"
        aria-label="Create Task Card Dialog"
      >
        <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
          <h3 className="text-sm font-bold text-foreground">
            Create Kanban Task Card
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label htmlFor="create-card-title" className="block text-xs font-semibold text-muted-foreground mb-1">
              Task Title
            </label>
            <input
              id="create-card-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Implement WebSocket reconnection protocol"
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
              required
            />
          </div>

          <div>
            <label htmlFor="create-card-desc" className="block text-xs font-semibold text-muted-foreground mb-1">
              Task Description & Criteria
            </label>
            <textarea
              id="create-card-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Detailed instructions for the specialist agent..."
              rows={2}
              className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="create-card-agent" className="block text-xs font-semibold text-muted-foreground mb-1">
                Assigned Specialist
              </label>
              <input
                id="create-card-agent"
                type="text"
                value={assignedAgent}
                onChange={(e) => setAssignedAgent(e.target.value)}
                placeholder="e.g. @backend-dev"
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
                required
              />
            </div>

            <div>
              <label htmlFor="create-card-priority" className="block text-xs font-semibold text-muted-foreground mb-1">
                Priority
              </label>
              <select
                id="create-card-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as CardPriority)}
                className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>

          <div>
            <span className="block text-xs font-semibold text-muted-foreground mb-1.5">
              Prerequisite DAG Dependencies (Card will be blocked until these complete)
            </span>
            {cardList.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">No existing cards to depend on.</p>
            ) : (
              <div className="max-h-32 overflow-y-auto rounded-md border border-border/50 bg-muted/20 p-2 space-y-1.5">
                {cardList.map((c) => (
                  <label
                    key={c.card_id}
                    className="flex items-center gap-2 text-xs text-foreground hover:bg-muted/40 p-1 rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedDeps.includes(c.card_id)}
                      onChange={() => handleToggleDep(c.card_id)}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    <span className="font-mono text-[11px] text-muted-foreground">{c.card_id.slice(-6)}</span>
                    <span className="truncate">{c.title}</span>
                    <span className="text-[10px] text-muted-foreground font-mono">({c.lane})</span>
                  </label>
                ))}
              </div>
            )}
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
              className="rounded-md bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs disabled:opacity-50"
            >
              {isProcessing ? 'Creating Card...' : 'Create Card'}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
};
