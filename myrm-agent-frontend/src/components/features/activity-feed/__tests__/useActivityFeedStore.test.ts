import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import type { ActivityFeedItem } from '../activityFeedTypes';
import { useActivityFeedStore } from '../useActivityFeedStore';

describe('useActivityFeedStore', () => {
  beforeEach(() => {
    act(() => {
      useActivityFeedStore.getState().resetStore();
    });
  });

  const mockItem1: ActivityFeedItem = {
    id: 'act_1',
    sourceSystem: 'email',
    sourceRefId: 'mail_99',
    title: '财务发票对账',
    summary: '收到增值税电子发票',
    autonomyTier: 'full_autonomous',
    status: 'pending_decision',
    timestamp: 1000,
    priority: 'normal',
  };

  const mockItem2: ActivityFeedItem = {
    id: 'act_2',
    sourceSystem: 'approval',
    sourceRefId: 'app_55',
    title: '高管权限放行',
    summary: '申请跨区域权限',
    autonomyTier: 'human_decision_required',
    status: 'pending_decision',
    timestamp: 2000,
    priority: 'urgent',
  };

  it('initializes with default state', () => {
    const state = useActivityFeedStore.getState();
    expect(state.items).toEqual([]);
    expect(state.archive).toEqual([]);
    expect(state.isEvaporationPaused).toBe(false);
    expect(state.filter.sourceSystem).toBe('all');
  });

  it('ingests and updates items', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
    });
    expect(useActivityFeedStore.getState().items.length).toBe(1);

    const updated: ActivityFeedItem = { ...mockItem1, title: '更新后的发票对账' };
    act(() => {
      useActivityFeedStore.getState().ingestItem(updated);
    });
    expect(useActivityFeedStore.getState().items.length).toBe(1);
    expect(useActivityFeedStore.getState().items[0].title).toBe('更新后的发票对账');
  });

  it('marks item as autonomous resolved and begins evaporation window', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
    });

    act(() => {
      useActivityFeedStore.getState().markAsAutonomousResolved('act_1', 4000);
    });

    const item = useActivityFeedStore.getState().items[0];
    expect(item.status).toBe('evaporating');
    expect(item.evaporationTtlMs).toBe(4000);
    expect(typeof item.resolvedAt).toBe('number');
  });

  it('evaporates item and moves it to archive', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
    });

    act(() => {
      useActivityFeedStore.getState().evaporateItem('act_1');
    });

    const state = useActivityFeedStore.getState();
    expect(state.items.length).toBe(0);
    expect(state.archive.length).toBe(1);
    expect(state.archive[0].id).toBe('act_1');
    expect(state.archive[0].status).toBe('evaporated');
    expect(typeof state.archive[0].evaporatedAt).toBe('number');
  });

  it('undoes evaporation and restores item from archive', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().evaporateItem('act_1');
    });

    expect(useActivityFeedStore.getState().archive.length).toBe(1);

    act(() => {
      useActivityFeedStore.getState().undoEvaporation('act_1');
    });

    const state = useActivityFeedStore.getState();
    expect(state.archive.length).toBe(0);
    expect(state.items.length).toBe(1);
    expect(state.items[0].id).toBe('act_1');
    expect(state.items[0].status).toBe('pending_decision');
  });

  it('handles human decisions: approve starts evaporation, reject marks dismissed', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem2);
    });

    // Test approve
    act(() => {
      useActivityFeedStore.getState().humanDecide('act_2', true);
    });
    expect(useActivityFeedStore.getState().items[0].status).toBe('evaporating');

    // Test reject
    act(() => {
      useActivityFeedStore.getState().humanDecide('act_2', false);
    });
    expect(useActivityFeedStore.getState().items[0].status).toBe('dismissed');
  });

  it('toggles pause evaporation state', () => {
    expect(useActivityFeedStore.getState().isEvaporationPaused).toBe(false);

    act(() => {
      useActivityFeedStore.getState().togglePauseEvaporation();
    });
    expect(useActivityFeedStore.getState().isEvaporationPaused).toBe(true);

    act(() => {
      useActivityFeedStore.getState().togglePauseEvaporation(false);
    });
    expect(useActivityFeedStore.getState().isEvaporationPaused).toBe(false);
  });

  it('clears archive and resets store', () => {
    act(() => {
      useActivityFeedStore.getState().ingestItem(mockItem1);
      useActivityFeedStore.getState().evaporateItem('act_1');
    });
    expect(useActivityFeedStore.getState().archive.length).toBe(1);

    act(() => {
      useActivityFeedStore.getState().clearArchive();
    });
    expect(useActivityFeedStore.getState().archive.length).toBe(0);

    act(() => {
      useActivityFeedStore.getState().resetStore();
    });
    expect(useActivityFeedStore.getState().items).toEqual([]);
  });
});
