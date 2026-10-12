import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as personCardService from '@/services/memory/personCard';
import { usePersonCard } from '../usePersonCard';

vi.mock('@/services/memory/personCard', () => ({
  listPersonCards: vi.fn(),
  getPersonCard: vi.fn(),
  createPersonCard: vi.fn(),
  updatePersonCard: vi.fn(),
  deletePersonCard: vi.fn(),
  mergePersonCards: vi.fn(),
  preActionCheck: vi.fn(),
  refreshPersonDecay: vi.fn(),
}));

describe('usePersonCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockCard: personCardService.PersonCardDTO = {
    person_id: 'p_01',
    display_name: '张三',
    aliases: ['三哥'],
    relation_type: 'friend',
    org: 'Acme',
    attributes: {
      dietary_restrictions: ['vegetarian'],
      birthday: '1990-01-01',
      timezone: 'UTC+8',
      preferred_contact_hours: '09:00-18:00',
      approval_preference: '微信',
      custom_notes: {},
    },
    commitments: ['周五交付'],
    interaction_timeline: [],
    last_interaction_at: '2026-10-10T00:00:00Z',
    confidence: 1.0,
    scope: 'global',
    agent_id: null,
    decay_status: 'active',
    decay_score: 1.0,
  };

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => usePersonCard());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.isChecking).toBe(false);
    expect(result.current.cards).toEqual([]);
    expect(result.current.selectedCard).toBeNull();
    expect(result.current.lastCheckResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('fetches cards successfully', async () => {
    vi.mocked(personCardService.listPersonCards).mockResolvedValueOnce([mockCard]);

    const { result } = renderHook(() => usePersonCard());

    let fetched: personCardService.PersonCardDTO[] = [];
    await act(async () => {
      fetched = await result.current.fetchCards({ query: '三哥' });
    });

    expect(fetched).toEqual([mockCard]);
    expect(result.current.cards).toEqual([mockCard]);
    expect(result.current.isLoading).toBe(false);
  });

  it('creates, updates, and deletes card correctly', async () => {
    vi.mocked(personCardService.createPersonCard).mockResolvedValueOnce(mockCard);

    const { result } = renderHook(() => usePersonCard());

    let created: personCardService.PersonCardDTO | null = null;
    await act(async () => {
      created = await result.current.createCard({
        display_name: '张三',
        aliases: ['三哥'],
        relation_type: 'friend',
      });
    });

    expect(created).toEqual(mockCard);
    expect(result.current.cards).toContainEqual(mockCard);

    // Update
    const updatedCard: personCardService.PersonCardDTO = {
      ...mockCard,
      display_name: '张三 (更新)',
    };
    vi.mocked(personCardService.updatePersonCard).mockResolvedValueOnce(updatedCard);

    let updated: personCardService.PersonCardDTO | null = null;
    await act(async () => {
      updated = await result.current.updateCard('p_01', {
        display_name: '张三 (更新)',
      });
    });

    expect((updated as unknown as personCardService.PersonCardDTO)?.display_name).toBe(
      '张三 (更新)'
    );
    expect(result.current.cards[0].display_name).toBe('张三 (更新)');

    // Delete
    vi.mocked(personCardService.deletePersonCard).mockResolvedValueOnce(undefined);

    let deleted = false;
    await act(async () => {
      deleted = await result.current.removeCard('p_01');
    });

    expect(deleted).toBe(true);
    expect(result.current.cards).toHaveLength(0);
  });

  it('merges two cards successfully', async () => {
    const cardA: personCardService.PersonCardDTO = {
      ...mockCard,
      person_id: 'p_01',
      display_name: '李四',
    };
    const cardB: personCardService.PersonCardDTO = {
      ...mockCard,
      person_id: 'p_02',
      display_name: '小李',
    };

    const mergedTarget: personCardService.PersonCardDTO = {
      ...cardB,
      aliases: ['李四', '小李'],
    };

    vi.mocked(personCardService.listPersonCards).mockResolvedValueOnce([cardA, cardB]);
    vi.mocked(personCardService.mergePersonCards).mockResolvedValueOnce(mergedTarget);

    const { result } = renderHook(() => usePersonCard());

    await act(async () => {
      await result.current.fetchCards();
    });
    expect(result.current.cards).toHaveLength(2);

    let merged: personCardService.PersonCardDTO | null = null;
    await act(async () => {
      merged = await result.current.mergeCards('p_01', 'p_02');
    });

    expect(merged).toEqual(mergedTarget);
    expect(result.current.cards).toHaveLength(1);
    expect(result.current.cards[0].person_id).toBe('p_02');
  });

  it('runs pre-action attribute verification check successfully', async () => {
    const mockCheckResult: personCardService.PreActionCheckResponseDTO = {
      action_type: 'send_invite',
      action_summary: '周末晚宴邀请',
      has_missing_attributes: true,
      has_weak_memory_warning: false,
      participants: [
        {
          person_id: 'p_01',
          display_name: '张三',
          relation_type: 'friend',
          dietary_restrictions: ['vegetarian'],
          missing_critical_attributes: [],
          is_weak_memory: false,
          attributes: mockCard.attributes,
        },
      ],
      prompt_cue: '【动作指引】准备执行：周末晚宴邀请\n本次涉及 1 位相关人：张三（忌口: vegetarian）。',
      warnings: [],
    };

    vi.mocked(personCardService.preActionCheck).mockResolvedValueOnce(mockCheckResult);

    const { result } = renderHook(() => usePersonCard());

    let res: personCardService.PreActionCheckResponseDTO | null = null;
    await act(async () => {
      res = await result.current.runPreActionCheck({
        action_type: 'send_invite',
        participant_names_or_ids: ['张三'],
        action_summary: '周末晚宴邀请',
      });
    });

    expect(res).toEqual(mockCheckResult);
    expect(result.current.lastCheckResult).toEqual(mockCheckResult);
    expect(result.current.isChecking).toBe(false);
  });

  it('recalculates gravity decay scores and refreshes cards', async () => {
    vi.mocked(personCardService.refreshPersonDecay).mockResolvedValueOnce({
      p_01: 0.85,
    });
    vi.mocked(personCardService.listPersonCards).mockResolvedValueOnce([mockCard]);

    const { result } = renderHook(() => usePersonCard());

    let decayScores: Record<string, number> | null = null;
    await act(async () => {
      decayScores = await result.current.recalculateDecay(0.3);
    });

    expect(decayScores).toEqual({ p_01: 0.85 });
    expect(result.current.cards).toEqual([mockCard]);
  });
});
