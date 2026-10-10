/**
 * [INPUT]
 * @/services/memory/personCard::DTOs, listPersonCards, getPersonCard, createPersonCard,
 *   updatePersonCard, deletePersonCard, mergePersonCards, preActionCheck, refreshPersonDecay
 * React::useState, useCallback
 *
 * [OUTPUT]
 * usePersonCard: React hook managing person entities, relationship profiles,
 *   gravity decay lifecycle, and pre-action attribute verification.
 *
 * [POS]
 * Hook module for Item 155 PersonCardAndRelationshipMemoryLayer.
 * Strict typing applied: 0 any types allowed.
 */

import { useCallback, useState } from 'react';
import {
  CreatePersonCardRequest,
  PersonCardDTO,
  PreActionCheckRequestDTO,
  PreActionCheckResponseDTO,
  RelationType,
  UpdatePersonCardRequest,
  createPersonCard,
  deletePersonCard,
  getPersonCard,
  listPersonCards,
  mergePersonCards,
  preActionCheck,
  refreshPersonDecay,
  updatePersonCard,
} from '@/services/memory/personCard';

export interface UsePersonCardState {
  isLoading: boolean;
  isChecking: boolean;
  cards: PersonCardDTO[];
  selectedCard: PersonCardDTO | null;
  lastCheckResult: PreActionCheckResponseDTO | null;
  error: string | null;
}

export interface UsePersonCardReturn extends UsePersonCardState {
  fetchCards: (params?: {
    query?: string;
    scope?: 'global' | 'agent';
    relation_type?: RelationType;
    include_weak?: boolean;
    include_archived?: boolean;
    agent_id?: string;
  }) => Promise<PersonCardDTO[]>;
  fetchCard: (personId: string) => Promise<PersonCardDTO | null>;
  createCard: (req: CreatePersonCardRequest) => Promise<PersonCardDTO | null>;
  updateCard: (personId: string, req: UpdatePersonCardRequest) => Promise<PersonCardDTO | null>;
  removeCard: (personId: string) => Promise<boolean>;
  mergeCards: (sourcePersonId: string, targetPersonId: string) => Promise<PersonCardDTO | null>;
  runPreActionCheck: (
    req: PreActionCheckRequestDTO
  ) => Promise<PreActionCheckResponseDTO | null>;
  recalculateDecay: (weakThreshold?: number) => Promise<Record<string, number> | null>;
  reset: () => void;
}

export function usePersonCard(): UsePersonCardReturn {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isChecking, setIsChecking] = useState<boolean>(false);
  const [cards, setCards] = useState<PersonCardDTO[]>([]);
  const [selectedCard, setSelectedCard] = useState<PersonCardDTO | null>(null);
  const [lastCheckResult, setLastCheckResult] = useState<PreActionCheckResponseDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchCards = useCallback(
    async (params?: {
      query?: string;
      scope?: 'global' | 'agent';
      relation_type?: RelationType;
      include_weak?: boolean;
      include_archived?: boolean;
      agent_id?: string;
    }): Promise<PersonCardDTO[]> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await listPersonCards(params);
        setCards(result);
        return result;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to list person cards';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchCard = useCallback(async (personId: string): Promise<PersonCardDTO | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const card = await getPersonCard(personId);
      setSelectedCard(card);
      return card;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : `Failed to fetch person card ${personId}`;
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createCard = useCallback(
    async (req: CreatePersonCardRequest): Promise<PersonCardDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const created = await createPersonCard(req);
        setCards((prev) => [created, ...prev]);
        return created;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to create person card';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const updateCard = useCallback(
    async (
      personId: string,
      req: UpdatePersonCardRequest
    ): Promise<PersonCardDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const updated = await updatePersonCard(personId, req);
        setCards((prev) => prev.map((c) => (c.person_id === personId ? updated : c)));
        if (selectedCard?.person_id === personId) {
          setSelectedCard(updated);
        }
        return updated;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : `Failed to update person card ${personId}`;
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [selectedCard]
  );

  const removeCard = useCallback(async (personId: string): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      await deletePersonCard(personId);
      setCards((prev) => prev.filter((c) => c.person_id !== personId));
      if (selectedCard?.person_id === personId) {
        setSelectedCard(null);
      }
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : `Failed to delete person card ${personId}`;
      setError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [selectedCard]);

  const mergeCards = useCallback(
    async (
      sourcePersonId: string,
      targetPersonId: string
    ): Promise<PersonCardDTO | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const merged = await mergePersonCards(sourcePersonId, targetPersonId);
        setCards((prev) =>
          prev
            .filter((c) => c.person_id !== sourcePersonId)
            .map((c) => (c.person_id === targetPersonId ? merged : c))
        );
        return merged;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to merge person cards';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const runPreActionCheck = useCallback(
    async (
      req: PreActionCheckRequestDTO
    ): Promise<PreActionCheckResponseDTO | null> => {
      setIsChecking(true);
      setError(null);
      try {
        const result = await preActionCheck(req);
        setLastCheckResult(result);
        return result;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to execute pre-action check';
        setError(message);
        return null;
      } finally {
        setIsChecking(false);
      }
    },
    []
  );

  const recalculateDecay = useCallback(
    async (weakThreshold = 0.3): Promise<Record<string, number> | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const scores = await refreshPersonDecay(weakThreshold);
        // Refresh cards to update active/weak status in UI
        const refreshed = await listPersonCards({ include_weak: true });
        setCards(refreshed);
        return scores;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to refresh person decay';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const reset = useCallback(() => {
    setIsLoading(false);
    setIsChecking(false);
    setCards([]);
    setSelectedCard(null);
    setLastCheckResult(null);
    setError(null);
  }, []);

  return {
    isLoading,
    isChecking,
    cards,
    selectedCard,
    lastCheckResult,
    error,
    fetchCards,
    fetchCard,
    createCard,
    updateCard,
    removeCard,
    mergeCards,
    runPreActionCheck,
    recalculateDecay,
    reset,
  };
}
