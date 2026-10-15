import React, { useState } from 'react';
import {
  CardArtifact,
  CardPriority,
  CreateCardInput,
  DEFAULT_BOARD_STATE,
  KanbanBoardState,
  KanbanCard,
  KanbanLane,
} from './kanban-orchestrator/types';
import { KanbanHeaderView } from './kanban-orchestrator/KanbanHeaderView';
import { KanbanSwimlanesBoardView } from './kanban-orchestrator/KanbanSwimlanesBoardView';
import { CardDetailDrawer } from './kanban-orchestrator/CardDetailDrawer';
import { DecomposeModalView } from './kanban-orchestrator/DecomposeModalView';
import { AddCardModalView } from './kanban-orchestrator/AddCardModalView';

export interface VisualMultiAgentKanbanCardProps {
  chatId: string;
  initialBoardState?: KanbanBoardState;
  onCreateCard?: (input: CreateCardInput) => Promise<KanbanCard>;
  onTransitionCard?: (
    cardId: string,
    lane: KanbanLane,
  ) => Promise<{ card: KanbanCard; unlocked_cards: string[] }>;
  onMountArtifact?: (
    cardId: string,
    name: string,
    artifactType: string,
    filePath?: string,
    preview?: string,
  ) => Promise<CardArtifact>;
  onHumanOverride?: (
    cardId: string,
    agent?: string,
    priority?: CardPriority,
    lane?: KanbanLane,
  ) => Promise<{ card: KanbanCard; unlocked_cards: string[] }>;
  onDecomposeGoal?: (goal: string, roster: string[]) => Promise<KanbanCard[]>;
  onRefresh?: () => Promise<void>;
}

export const VisualMultiAgentKanbanCard: React.FC<VisualMultiAgentKanbanCardProps> = ({
  chatId,
  initialBoardState = DEFAULT_BOARD_STATE,
  onCreateCard,
  onTransitionCard,
  onMountArtifact,
  onHumanOverride,
  onDecomposeGoal,
  onRefresh,
}) => {
  const [boardState, setBoardState] = useState<KanbanBoardState>(initialBoardState);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [isAddCardOpen, setIsAddCardOpen] = useState<boolean>(false);
  const [isDecomposeOpen, setIsDecomposeOpen] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<string>(
    'Kanban orchestrator ready: 6-swimlane workflow active with automatic DAG dependency unblocking.',
  );

  const cardList = Object.values(boardState.cards);
  const doneCardsCount = cardList.filter((c) => c.lane === 'done').length;
  const blockedCardsCount = cardList.filter((c) => c.lane === 'blocked').length;

  const handleQuickTransition = async (cardId: string, targetLane: KanbanLane) => {
    setIsProcessing(true);
    setStatusMessage(`Moving card '${cardId}' to '${targetLane}'...`);
    try {
      if (onTransitionCard) {
        const res = await onTransitionCard(cardId, targetLane);
        setBoardState((prev) => {
          const copy = { ...prev.cards, [cardId]: res.card };
          for (const uId of res.unlocked_cards) {
            if (copy[uId]) {
              copy[uId] = { ...copy[uId], lane: 'todo', blocked_by: [] };
            }
          }
          return { ...prev, cards: copy, updated_at: Date.now() };
        });
        const unlockNotice = res.unlocked_cards.length > 0 ? ` (Auto-unblocked: ${res.unlocked_cards.join(', ')})` : '';
        setStatusMessage(`Card '${cardId}' moved to '${targetLane}'${unlockNotice}.`);
      } else {
        // Fallback local simulation
        setBoardState((prev) => {
          const target = prev.cards[cardId];
          if (!target) {
            return prev;
          }
          const updated = {
            ...target,
            lane: targetLane,
            updated_at: Date.now(),
            completed_at: targetLane === 'done' ? Date.now() : target.completed_at,
          };
          const copy = { ...prev.cards, [cardId]: updated };

          // If moving to done, auto-unblock downstream cards
          let unlockedCount = 0;
          if (targetLane === 'done') {
            for (const otherId in copy) {
              const other = copy[otherId];
              if (other.depends_on.includes(cardId) && other.lane === 'blocked') {
                const remainingBlocked = other.depends_on.filter(
                  (dId) => dId !== cardId && copy[dId]?.lane !== 'done',
                );
                if (remainingBlocked.length === 0) {
                  copy[otherId] = { ...other, lane: 'todo', blocked_by: [] };
                  unlockedCount++;
                }
              }
            }
          }
          setStatusMessage(
            `Card '${cardId}' updated to '${targetLane}'${unlockedCount > 0 ? ` (${unlockedCount} card(s) auto-unblocked)` : ''}.`,
          );
          return { ...prev, cards: copy, updated_at: Date.now() };
        });
      }
    } catch (err) {
      setStatusMessage(`Transition failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCreateCard = async (input: CreateCardInput) => {
    setIsProcessing(true);
    setStatusMessage(`Creating task card '${input.title}'...`);
    try {
      if (onCreateCard) {
        const newCard = await onCreateCard(input);
        setBoardState((prev) => ({
          ...prev,
          cards: { ...prev.cards, [newCard.card_id]: newCard },
          updated_at: Date.now(),
        }));
        setStatusMessage(`Card '${newCard.title}' created in lane '${newCard.lane}'.`);
      } else {
        const cardId = `card-custom-${Date.now().toString().slice(-4)}`;
        const hasUnresolvedDeps = input.depends_on.some(
          (d) => boardState.cards[d]?.lane !== 'done',
        );
        const newCard: KanbanCard = {
          card_id: cardId,
          board_id: boardState.board_id,
          title: input.title,
          description: input.description,
          lane: hasUnresolvedDeps ? 'blocked' : 'todo',
          priority: input.priority,
          assigned_agent: input.assigned_agent,
          depends_on: input.depends_on,
          blocked_by: hasUnresolvedDeps
            ? input.depends_on.filter((d) => boardState.cards[d]?.lane !== 'done')
            : [],
          sandbox_subdir: `tasks/${cardId}`,
          artifacts: [],
          created_at: Date.now(),
          updated_at: Date.now(),
        };
        setBoardState((prev) => ({
          ...prev,
          cards: { ...prev.cards, [cardId]: newCard },
          updated_at: Date.now(),
        }));
        setStatusMessage(`Card '${input.title}' created (${newCard.lane}).`);
      }
      setIsAddCardOpen(false);
    } catch (err) {
      setStatusMessage(`Create card failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleMountArtifact = async (
    cardId: string,
    name: string,
    artifactType: string,
    filePath?: string,
    preview?: string,
  ) => {
    setStatusMessage(`Mounting artifact '${name}' to card '${cardId}'...`);
    try {
      if (onMountArtifact) {
        const art = await onMountArtifact(cardId, name, artifactType, filePath, preview);
        setBoardState((prev) => {
          const card = prev.cards[cardId];
          if (!card) {
            return prev;
          }
          return {
            ...prev,
            cards: {
              ...prev.cards,
              [cardId]: {
                ...card,
                artifacts: [...card.artifacts, art],
                updated_at: Date.now(),
              },
            },
          };
        });
        setStatusMessage(`Artifact '${name}' successfully mounted.`);
      } else {
        const newArt: CardArtifact = {
          artifact_id: `art-${Date.now().toString().slice(-4)}`,
          name,
          artifact_type: artifactType,
          file_path: filePath,
          content_preview: preview,
          mounted_at: Date.now(),
        };
        setBoardState((prev) => {
          const card = prev.cards[cardId];
          if (!card) {
            return prev;
          }
          return {
            ...prev,
            cards: {
              ...prev.cards,
              [cardId]: {
                ...card,
                artifacts: [...card.artifacts, newArt],
                updated_at: Date.now(),
              },
            },
          };
        });
        setStatusMessage(`Artifact '${name}' attached.`);
      }
    } catch (err) {
      setStatusMessage(`Mount artifact failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleHumanOverride = async (
    cardId: string,
    agent?: string,
    priority?: CardPriority,
    lane?: KanbanLane,
  ) => {
    setIsProcessing(true);
    setStatusMessage(`Applying human-in-the-loop override for '${cardId}'...`);
    try {
      if (onHumanOverride) {
        const res = await onHumanOverride(cardId, agent, priority, lane);
        setBoardState((prev) => ({
          ...prev,
          cards: { ...prev.cards, [cardId]: res.card },
          updated_at: Date.now(),
        }));
        setStatusMessage(`Override applied for card '${cardId}'.`);
      } else {
        setBoardState((prev) => {
          const card = prev.cards[cardId];
          if (!card) {
            return prev;
          }
          return {
            ...prev,
            cards: {
              ...prev.cards,
              [cardId]: {
                ...card,
                assigned_agent: agent || card.assigned_agent,
                priority: priority || card.priority,
                lane: lane || card.lane,
                updated_at: Date.now(),
              },
            },
          };
        });
        setStatusMessage(`Card '${cardId}' overridden by human supervisor.`);
      }
    } catch (err) {
      setStatusMessage(`Override failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDecomposeGoal = async (goal: string, roster: string[]) => {
    setIsProcessing(true);
    setStatusMessage(`Boss Agent decomposing goal into sequenced DAG cards...`);
    try {
      if (onDecomposeGoal) {
        const createdCards = await onDecomposeGoal(goal, roster);
        setBoardState((prev) => {
          const copy = { ...prev.cards };
          for (const c of createdCards) {
            copy[c.card_id] = c;
          }
          return { ...prev, cards: copy, updated_at: Date.now() };
        });
        setStatusMessage(`Boss Agent generated ${createdCards.length} sequenced DAG cards.`);
      } else {
        // Fallback simulated decomposition
        const c1Id = `card-dag-${Date.now().toString().slice(-4)}-1`;
        const c2Id = `card-dag-${Date.now().toString().slice(-4)}-2`;
        const c1: KanbanCard = {
          card_id: c1Id,
          board_id: boardState.board_id,
          title: `Spec: ${goal.slice(0, 30)}`,
          description: `Analyze requirements and output architecture contracts.`,
          lane: 'todo',
          priority: 'high',
          assigned_agent: roster[0] || '@architect',
          depends_on: [],
          blocked_by: [],
          sandbox_subdir: `tasks/${c1Id}`,
          artifacts: [],
          created_at: Date.now(),
          updated_at: Date.now(),
        };
        const c2: KanbanCard = {
          card_id: c2Id,
          board_id: boardState.board_id,
          title: `Build: ${goal.slice(0, 30)}`,
          description: `Implement services based on architecture spec.`,
          lane: 'blocked',
          priority: 'high',
          assigned_agent: roster[1] || '@backend-dev',
          depends_on: [c1Id],
          blocked_by: [c1Id],
          sandbox_subdir: `tasks/${c2Id}`,
          artifacts: [],
          created_at: Date.now(),
          updated_at: Date.now(),
        };
        setBoardState((prev) => ({
          ...prev,
          cards: { ...prev.cards, [c1Id]: c1, [c2Id]: c2 },
          updated_at: Date.now(),
        }));
        setStatusMessage(`Boss Agent generated 2 sequenced DAG cards.`);
      }
      setIsDecomposeOpen(false);
    } catch (err) {
      setStatusMessage(`Decomposition failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRefresh = async () => {
    if (!onRefresh) {
      return;
    }
    setIsProcessing(true);
    setStatusMessage('Refreshing multi-agent Kanban board...');
    try {
      await onRefresh();
      setStatusMessage('Board state refreshed.');
    } catch (err) {
      setStatusMessage(`Refresh failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const selectedCard = selectedCardId ? boardState.cards[selectedCardId] || null : null;

  return (
    <article
      aria-label="Visual Multi-Agent Kanban Card"
      data-chat-id={chatId}
      className="my-3 overflow-hidden rounded-xl border border-border/60 bg-background/95 p-4 shadow-sm backdrop-blur-xs space-y-4"
    >
      <KanbanHeaderView
        title={boardState.title}
        totalCards={cardList.length}
        doneCards={doneCardsCount}
        blockedCards={blockedCardsCount}
        isProcessing={isProcessing}
        onOpenDecompose={() => setIsDecomposeOpen(true)}
        onOpenAddCard={() => setIsAddCardOpen(true)}
        onRefresh={onRefresh ? handleRefresh : undefined}
      />

      <div className="rounded-lg bg-muted/30 px-3 py-2 text-xs border border-border/30">
        <output aria-live="polite" className="flex items-center gap-2 text-foreground/90">
          <span className="font-semibold text-primary">Status:</span>
          <span>{statusMessage}</span>
        </output>
      </div>

      <KanbanSwimlanesBoardView
        cards={boardState.cards}
        onCardClick={(id) => setSelectedCardId(id)}
        onQuickTransition={handleQuickTransition}
      />

      <CardDetailDrawer
        card={selectedCard}
        allCards={boardState.cards}
        onClose={() => setSelectedCardId(null)}
        onTransition={handleQuickTransition}
        onHumanOverride={handleHumanOverride}
        onMountArtifact={handleMountArtifact}
      />

      <DecomposeModalView
        isOpen={isDecomposeOpen}
        isProcessing={isProcessing}
        onClose={() => setIsDecomposeOpen(false)}
        onDecompose={handleDecomposeGoal}
      />

      <AddCardModalView
        isOpen={isAddCardOpen}
        isProcessing={isProcessing}
        existingCards={boardState.cards}
        onClose={() => setIsAddCardOpen(false)}
        onCreateCard={handleCreateCard}
      />
    </article>
  );
};
