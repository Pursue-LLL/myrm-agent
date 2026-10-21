import { describe, it, expect } from 'vitest';
import type {
  AttentionPriority,
  AttentionCategory,
  AttentionItem,
  AttentionFilterState,
  AttentionCategoryMeta,
  AttentionHubStoreState,
} from '../attentionHubTypes';

describe('attentionHubTypes', () => {
  it('correctly models AttentionItem contract', () => {
    const item: AttentionItem = {
      id: 'att_1',
      chatId: 'chat_101',
      chatTitle: '重构前端工程',
      category: 'approval_blocking',
      priority: 'urgent',
      title: '高危文件写入审批',
      description: '智能体请求修改核心配置文件',
      timestamp: 1760000000000,
      expiresAt: 1760000060000,
      targetAnchorNodeId: 'msg_999',
      isRead: false,
      actionRequired: true,
    };

    expect(item.id).toBe('att_1');
    expect(item.category).toBe<AttentionCategory>('approval_blocking');
    expect(item.priority).toBe<AttentionPriority>('urgent');
    expect(item.actionRequired).toBe(true);
  });

  it('correctly models AttentionFilterState contract', () => {
    const filter: AttentionFilterState = {
      category: 'approval_blocking',
      onlyActionRequired: true,
      searchQuery: '审批',
    };

    expect(filter.category).toBe('approval_blocking');
    expect(filter.onlyActionRequired).toBe(true);
    expect(filter.searchQuery).toBe('审批');
  });

  it('correctly models AttentionCategoryMeta contract', () => {
    const meta: AttentionCategoryMeta = {
      category: 'task_failed',
      label: '任务异常',
      badgeColor: 'orange',
    };

    expect(meta.category).toBe('task_failed');
    expect(meta.badgeColor).toBe('orange');
  });

  it('correctly models AttentionHubStoreState contract', () => {
    const state: AttentionHubStoreState = {
      items: [],
      isPanelOpen: false,
      filter: {
        category: 'all',
        onlyActionRequired: false,
        searchQuery: '',
      },
    };

    expect(state.items).toEqual([]);
    expect(state.isPanelOpen).toBe(false);
  });
});
