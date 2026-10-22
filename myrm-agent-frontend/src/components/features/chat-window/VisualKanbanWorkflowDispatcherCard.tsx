import React, { useId, useState } from 'react';
import {
  INITIAL_DEMO_CARDS,
  KanbanCardItem,
  KanbanSwimlane,
  SWIMLANE_CONFIG,
  SWIMLANE_ORDER,
  VisualKanbanWorkflowDispatcherCardProps,
} from './kanban-dispatcher/types';

export const VisualKanbanWorkflowDispatcherCard: React.FC<
  VisualKanbanWorkflowDispatcherCardProps
> = ({
  chatId,
  initialCards = INITIAL_DEMO_CARDS,
  onDismiss,
  onCardHandoff,
  onCardToggleBlock,
  onCardCreated,
}) => {
  const [cards, setCards] = useState<KanbanCardItem[]>(initialCards);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [isAddingCard, setIsAddingCard] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDesc, setNewDesc] = useState<string>('');
  const [newTags, setNewTags] = useState<string>('');
  const [announcement, setAnnouncement] = useState<string>('Kanban board loaded');

  const titleInputId = useId();
  const descInputId = useId();
  const tagsInputId = useId();

  const totalCards = cards.length;
  const blockedCards = cards.filter((c) => c.isBlocked);
  const doneCards = cards.filter((c) => c.swimlane === 'done');

  const handleHandoff = (card: KanbanCardItem) => {
    const currentIdx = SWIMLANE_ORDER.indexOf(card.swimlane);
    if (currentIdx >= SWIMLANE_ORDER.length - 1) {
      return;
    }
    const nextLane = SWIMLANE_ORDER[currentIdx + 1];
    const nextAgent = SWIMLANE_CONFIG[nextLane].defaultAgent;
    const nowIso = new Date().toISOString();

    const updatedCard: KanbanCardItem = {
      ...card,
      swimlane: nextLane,
      assignedAgentId: nextAgent,
      progressPct: Math.min(100, Math.round(((currentIdx + 2) / SWIMLANE_ORDER.length) * 100)),
      isBlocked: false,
      blockReason: undefined,
      updatedAtUtc: nowIso,
      handoffHistory: [
        ...card.handoffHistory,
        {
          fromLane: card.swimlane,
          toLane: nextLane,
          fromAgent: card.assignedAgentId,
          toAgent: nextAgent,
          timestampUtc: nowIso,
          notes: `Automated handoff from ${card.swimlane} to ${nextLane}.`,
        },
      ],
    };

    setCards((prev) => prev.map((c) => (c.cardId === card.cardId ? updatedCard : c)));
    setAnnouncement(`Card ${card.cardId} handed off to ${nextLane} assigned to ${nextAgent}.`);
    onCardHandoff?.(card.cardId, nextLane, nextAgent);
  };

  const handleToggleBlock = (card: KanbanCardItem) => {
    const nextBlocked = !card.isBlocked;
    const reason = nextBlocked ? 'Blocked by dependency or review request' : undefined;
    const nowIso = new Date().toISOString();

    const updatedCard: KanbanCardItem = {
      ...card,
      isBlocked: nextBlocked,
      blockReason: reason,
      updatedAtUtc: nowIso,
    };

    setCards((prev) => prev.map((c) => (c.cardId === card.cardId ? updatedCard : c)));
    setAnnouncement(`Card ${card.cardId} is now ${nextBlocked ? 'blocked' : 'unblocked'}.`);
    onCardToggleBlock?.(card.cardId, nextBlocked, reason);
  };

  const handleCreateCard = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) {
      return;
    }
    const nowIso = new Date().toISOString();
    const created: KanbanCardItem = {
      cardId: `card-${Date.now().toString(36)}`,
      title: newTitle.trim(),
      description: newDesc.trim() || 'No detailed description provided.',
      swimlane: 'backlog',
      assignedAgentId: SWIMLANE_CONFIG.backlog.defaultAgent,
      progressPct: 10,
      isBlocked: false,
      handoffHistory: [],
      tags: newTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      createdAtUtc: nowIso,
      updatedAtUtc: nowIso,
    };

    setCards((prev) => [created, ...prev]);
    setNewTitle('');
    setNewDesc('');
    setNewTags('');
    setIsAddingCard(false);
    setAnnouncement(`Created new card: ${created.title}`);
    onCardCreated?.(created);
  };

  return (
    <section
      aria-label="Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff"
      className="p-4 bg-slate-900/90 border border-slate-700/80 rounded-xl shadow-xl text-slate-100 flex flex-col gap-4 text-xs font-sans"
    >
      <header className="flex flex-wrap items-center justify-between border-b border-slate-700/60 pb-3 gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-indigo-400">📋 Visual Kanban Dispatcher</span>
          {chatId && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              Session: {chatId}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
            Total: <strong>{totalCards}</strong>
          </span>
          <span
            className={`px-2 py-0.5 rounded border ${
              blockedCards.length > 0
                ? 'bg-rose-950/60 text-rose-300 border-rose-700 font-bold'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
          >
            Blocked: <strong>{blockedCards.length}</strong>
          </span>
          <span className="px-2 py-0.5 rounded bg-emerald-950/40 text-emerald-300 border border-emerald-800">
            Done: <strong>{doneCards.length}</strong>
          </span>
          <button
            type="button"
            onClick={() => setIsAddingCard(!isAddingCard)}
            className="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors"
          >
            {isAddingCard ? 'Cancel' : '+ New Card'}
          </button>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss Kanban Board"
              className="text-slate-400 hover:text-white px-2 py-0.5 rounded hover:bg-slate-800"
            >
              ✕
            </button>
          )}
        </div>
      </header>

      {/* Accessible live region */}
      <output aria-live="polite" className="sr-only">
        {announcement}
      </output>

      {/* New Card Form */}
      {isAddingCard && (
        <form
          onSubmit={handleCreateCard}
          className="p-3 bg-slate-800/80 border border-indigo-500/50 rounded-lg flex flex-col gap-2"
        >
          <div className="font-semibold text-indigo-300">Create New Workflow Card</div>
          <div className="flex flex-col gap-1">
            <label htmlFor={titleInputId} className="text-slate-300">
              Task Title
            </label>
            <input
              id={titleInputId}
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Implement distributed consensus check"
              className="px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-100 focus:outline-none focus:border-indigo-400"
              required
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={descInputId} className="text-slate-300">
              Description
            </label>
            <textarea
              id={descInputId}
              rows={2}
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Details on scope and criteria..."
              className="px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-100 focus:outline-none focus:border-indigo-400"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={tagsInputId} className="text-slate-300">
              Tags (comma separated)
            </label>
            <input
              id={tagsInputId}
              type="text"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              placeholder="e.g. core, p0, review"
              className="px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-slate-100 focus:outline-none focus:border-indigo-400"
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setIsAddingCard(false)}
              className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
            >
              Dispatch to Backlog
            </button>
          </div>
        </form>
      )}

      {/* 5 Swimlanes Grid */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
        {SWIMLANE_ORDER.map((lane) => {
          const config = SWIMLANE_CONFIG[lane];
          const laneCards = cards.filter((c) => c.swimlane === lane);

          return (
            <div
              key={lane}
              className={`flex flex-col rounded-lg border p-2.5 gap-2 min-h-[220px] ${config.color}`}
            >
              <div className="flex items-center justify-between font-semibold border-b border-slate-700/40 pb-1.5">
                <span>{config.label}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-900/60 border border-slate-700">
                  {laneCards.length}
                </span>
              </div>
              <div className="text-[10px] text-slate-400 flex items-center gap-1">
                <span>Default:</span>
                <span className="font-mono text-slate-300">{config.defaultAgent}</span>
              </div>

              {/* Cards in this lane */}
              <div className="flex flex-col gap-2 flex-1">
                {laneCards.length === 0 ? (
                  <div className="text-[11px] text-slate-500 italic py-4 text-center">
                    No active cards
                  </div>
                ) : (
                  laneCards.map((card) => {
                    const isSelected = selectedCardId === card.cardId;
                    const canHandoff = lane !== 'done';

                    return (
                      <div
                        key={card.cardId}
                        className={`p-2.5 rounded border transition-all flex flex-col gap-1.5 bg-slate-900/95 ${
                          card.isBlocked
                            ? 'border-rose-500/80 shadow-rose-950/20 shadow-md'
                            : 'border-slate-700 hover:border-indigo-400/60'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-1">
                          <span className="font-medium text-slate-200 line-clamp-2">
                            {card.title}
                          </span>
                          {card.isBlocked && (
                            <span
                              title={card.blockReason || 'Blocked'}
                              className="px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 font-bold text-[9px] shrink-0"
                            >
                              BLOCKED
                            </span>
                          )}
                        </div>

                        <p className="text-[11px] text-slate-400 line-clamp-2">
                          {card.description}
                        </p>

                        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1">
                          <span className="font-mono text-cyan-400">
                            @{card.assignedAgentId}
                          </span>
                          <span>{card.progressPct}%</span>
                        </div>

                        {/* Progress Bar */}
                        <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              card.isBlocked
                                ? 'bg-rose-500'
                                : card.swimlane === 'done'
                                ? 'bg-emerald-500'
                                : 'bg-indigo-500'
                            }`}
                            style={{ width: `${card.progressPct}%` }}
                          />
                        </div>

                        {/* Tags */}
                        {card.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {card.tags.map((t) => (
                              <span
                                key={t}
                                className="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700"
                              >
                                #{t}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Action buttons */}
                        <div className="flex items-center justify-between gap-1 pt-1.5 border-t border-slate-800 mt-1">
                          <button
                            type="button"
                            onClick={() => handleToggleBlock(card)}
                            className={`px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                              card.isBlocked
                                ? 'bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-700'
                                : 'bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-800'
                            }`}
                          >
                            {card.isBlocked ? 'Unblock' : 'Block'}
                          </button>

                          <div className="flex items-center gap-1">
                            <button
                              type="button"
                              onClick={() =>
                                setSelectedCardId(isSelected ? null : card.cardId)
                              }
                              className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                            >
                              {isSelected ? 'Hide' : 'Log'}
                            </button>

                            {canHandoff && (
                              <button
                                type="button"
                                onClick={() => handleHandoff(card)}
                                className="px-2 py-0.5 rounded text-[10px] bg-indigo-600 hover:bg-indigo-500 text-white font-medium"
                              >
                                Handoff →
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Handoff History Drawer */}
                        {isSelected && (
                          <div className="mt-2 p-2 rounded bg-slate-950 border border-slate-800 text-[10px] flex flex-col gap-1">
                            <div className="font-semibold text-slate-300 border-b border-slate-800 pb-0.5">
                              Handoff History ({card.handoffHistory.length})
                            </div>
                            {card.handoffHistory.length === 0 ? (
                              <span className="text-slate-500 italic">No handoffs yet</span>
                            ) : (
                              card.handoffHistory.map((h, idx) => (
                                <div key={idx} className="flex flex-col text-slate-400">
                                  <span>
                                    {h.fromLane} ({h.fromAgent}) → {h.toLane} ({h.toAgent})
                                  </span>
                                  {h.notes && (
                                    <span className="text-[9px] text-slate-500 italic">
                                      {h.notes}
                                    </span>
                                  )}
                                </div>
                              ))
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};
