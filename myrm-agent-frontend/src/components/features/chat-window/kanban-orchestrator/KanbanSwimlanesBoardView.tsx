import React from 'react';
import { CardPriority, KANBAN_LANES, KanbanCard, KanbanLane } from './types';

export interface KanbanSwimlanesBoardViewProps {
  cards: Record<string, KanbanCard>;
  onCardClick: (cardId: string) => void;
  onQuickTransition: (cardId: string, targetLane: KanbanLane) => void;
}

export const KanbanSwimlanesBoardView: React.FC<KanbanSwimlanesBoardViewProps> = ({
  cards,
  onCardClick,
  onQuickTransition,
}) => {
  const cardList = Object.values(cards);

  const getPriorityBadge = (priority: CardPriority) => {
    switch (priority) {
      case 'critical':
        return <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-rose-500 border border-rose-500/20">Critical</span>;
      case 'high':
        return <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-500 border border-amber-500/20">High</span>;
      case 'medium':
        return <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue-500 border border-blue-500/20">Medium</span>;
      case 'low':
      default:
        return <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground border border-border">Low</span>;
    }
  };

  const getNextLane = (current: KanbanLane): KanbanLane | null => {
    switch (current) {
      case 'backlog':
        return 'todo';
      case 'todo':
        return 'in_progress';
      case 'in_progress':
        return 'review';
      case 'review':
        return 'done';
      case 'blocked':
        return null;
      case 'done':
        return null;
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 pt-2">
      {KANBAN_LANES.map((lane) => {
        const laneCards = cardList.filter((c) => c.lane === lane.id);

        return (
          <div
            key={lane.id}
            className="flex flex-col rounded-lg border border-border/50 bg-muted/20 p-2.5 min-h-[320px]"
          >
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/30">
              <span className={`text-xs font-bold tracking-tight ${lane.color}`}>
                {lane.label}
              </span>
              <span className="rounded-full bg-muted/80 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                {laneCards.length}
              </span>
            </div>

            <div className="flex-1 space-y-2.5 overflow-y-auto">
              {laneCards.length === 0 ? (
                <div className="flex items-center justify-center h-28 text-[11px] text-muted-foreground/60 italic border border-dashed border-border/40 rounded-md">
                  Empty
                </div>
              ) : (
                laneCards.map((card) => {
                  const nextLane = getNextLane(card.lane);
                  const isBlocked = card.lane === 'blocked' || card.blocked_by.length > 0;

                  return (
                    <div
                      key={card.card_id}
                      className="rounded-md border border-border/60 bg-card p-2.5 shadow-xs space-y-2"
                    >
                      <div className="flex items-start justify-between gap-1.5">
                        <button
                          type="button"
                          onClick={() => onCardClick(card.card_id)}
                          className="text-left text-xs font-semibold text-foreground line-clamp-2 hover:text-primary transition-colors focus:outline-none focus:underline"
                        >
                          {card.title}
                        </button>
                        {getPriorityBadge(card.priority)}
                      </div>

                      <div className="flex items-center justify-between text-[11px] font-mono">
                        <span className="rounded bg-indigo-500/10 text-indigo-500 px-1.5 py-0.5 font-medium border border-indigo-500/20">
                          {card.assigned_agent}
                        </span>
                        <span className="text-[10px] text-muted-foreground">
                          {card.sandbox_subdir}
                        </span>
                      </div>

                      {card.depends_on.length > 0 && (
                        <div className="flex flex-wrap gap-1 text-[10px]">
                          <span className="text-muted-foreground">deps:</span>
                          {card.depends_on.map((d) => (
                            <span
                              key={d}
                              className={`rounded px-1 py-0.2 font-mono ${
                                card.blocked_by.includes(d)
                                  ? 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                                  : 'bg-muted text-muted-foreground'
                              }`}
                            >
                              {d.slice(-6)}
                            </span>
                          ))}
                        </div>
                      )}

                      {card.artifacts.length > 0 && (
                        <div className="flex items-center gap-1 text-[10px] font-mono text-emerald-500">
                          <span>📦</span>
                          <span>{card.artifacts.length} artifact(s)</span>
                        </div>
                      )}

                      <div className="pt-1.5 border-t border-border/30 flex items-center justify-between">
                        <span className="text-[10px] text-muted-foreground">
                          {card.card_id.slice(-6)}
                        </span>
                        {nextLane && !isBlocked && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onQuickTransition(card.card_id, nextLane);
                            }}
                            className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-foreground hover:bg-primary hover:text-primary-foreground transition-colors"
                          >
                            Advance →
                          </button>
                        )}
                        {card.lane === 'review' && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onQuickTransition(card.card_id, 'done');
                            }}
                            className="rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium hover:bg-emerald-500 hover:text-white transition-colors"
                          >
                            ✓ Approve
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
