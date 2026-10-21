import { describe, it, expect, beforeEach } from 'vitest';
import { useFinalCardStore } from '../useFinalCardStore';
import { assembleFinalCardContract } from '../finalCardEngine';

describe('useFinalCardStore', () => {
  beforeEach(() => {
    useFinalCardStore.getState().resetStore();
  });

  it('initializes with default state', () => {
    const state = useFinalCardStore.getState();
    expect(state.cards).toEqual({});
    expect(state.activeTranscriptCardId).toBeNull();
  });

  it('upserts and retrieves card by turnId', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-999',
      title: '编译成功',
      summary: '全部模块无告警',
    });

    useFinalCardStore.getState().upsertCard(card);

    const stored = useFinalCardStore.getState().getCardByTurnId('turn-999');
    expect(stored).toBeDefined();
    expect(stored?.title).toBe('编译成功');
    expect(useFinalCardStore.getState().cards[card.id]).toEqual(card);
  });

  it('removes card and resets activeTranscriptCardId if matching', () => {
    const card = assembleFinalCardContract({
      turnId: 'turn-888',
      title: '待删除卡片',
      summary: '测试删除',
    });

    useFinalCardStore.getState().upsertCard(card);
    useFinalCardStore.getState().openTranscriptModal(card.id);
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBe(card.id);

    useFinalCardStore.getState().removeCard(card.id);
    expect(useFinalCardStore.getState().cards[card.id]).toBeUndefined();
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();
  });

  it('clears all cards and closes modal', () => {
    const card1 = assembleFinalCardContract({
      turnId: 'turn-1',
      title: '卡片1',
      summary: '摘要1',
    });
    const card2 = assembleFinalCardContract({
      turnId: 'turn-2',
      title: '卡片2',
      summary: '摘要2',
    });

    useFinalCardStore.getState().upsertCard(card1);
    useFinalCardStore.getState().upsertCard(card2);
    useFinalCardStore.getState().openTranscriptModal(card1.id);

    useFinalCardStore.getState().clearCards();
    expect(useFinalCardStore.getState().cards).toEqual({});
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();
  });

  it('handles open and close modal transitions', () => {
    useFinalCardStore.getState().openTranscriptModal('card-arbitrary');
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBe('card-arbitrary');

    useFinalCardStore.getState().closeTranscriptModal();
    expect(useFinalCardStore.getState().activeTranscriptCardId).toBeNull();
  });
});
