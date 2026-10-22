import { describe, it, expect, beforeEach } from 'vitest';
import {
  useHandoffBriefStore,
  buildHandoffContextPrompt,
} from '../useHandoffBriefStore';
import type { HandoffBrief } from '../handoffBriefTypes';

describe('useHandoffBriefStore', () => {
  beforeEach(() => {
    useHandoffBriefStore.getState().reset();
  });

  const mockBrief: HandoffBrief = {
    sessionId: 'session-prev-101',
    sessionTitle: '重构认证服务与 Token 刷新',
    summary: '完成 JWT 刷新与前端拦截器重构，遗留 Redis 黑名单下线任务。',
    precomputedAt: Date.now(),
    precomputeDurationMs: 14,
    artifacts: ['src/services/auth.ts'],
    items: [
      {
        id: 'item-1',
        category: 'decision',
        content: '采用双 Token 架构（Access 15m + Refresh 7d）',
        enabled: true,
      },
      {
        id: 'item-2',
        category: 'todo',
        content: '对接 Redis 黑名单失效逻辑',
        enabled: true,
      },
      {
        id: 'item-3',
        category: 'constraint',
        content: '严格禁用 Cookie 明文传输，必须携带 SameSite=Strict',
        enabled: true,
      },
    ],
  };

  it('stores and retrieves precomputed brief', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    expect(useHandoffBriefStore.getState().briefs['session-prev-101']).toEqual(mockBrief);
  });

  it('toggles item enabled state correctly', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().toggleItem('session-prev-101', 'item-2');

    const updated = useHandoffBriefStore.getState().briefs['session-prev-101'];
    expect(updated.items.find((i) => i.id === 'item-2')?.enabled).toBe(false);
  });

  it('toggles all items enabled state', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().toggleAllItems('session-prev-101', false);

    const updated = useHandoffBriefStore.getState().briefs['session-prev-101'];
    expect(updated.items.every((i) => !i.enabled)).toBe(true);

    useHandoffBriefStore.getState().toggleAllItems('session-prev-101', true);
    expect(useHandoffBriefStore.getState().briefs['session-prev-101'].items.every((i) => i.enabled)).toBe(true);
  });

  it('updates item content in place', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().updateItemContent('session-prev-101', 'item-1', '采用双 Token + 设备指纹架构');

    const item = useHandoffBriefStore.getState().briefs['session-prev-101'].items.find((i) => i.id === 'item-1');
    expect(item?.content).toBe('采用双 Token + 设备指纹架构');
  });

  it('adds and removes custom items', () => {
    useHandoffBriefStore.getState().setBrief(mockBrief);
    useHandoffBriefStore.getState().addItem('session-prev-101', 'decision', '补充决策：优先使用 Ed25519 签名');

    const items = useHandoffBriefStore.getState().briefs['session-prev-101'].items;
    expect(items).toHaveLength(4);
    const added = items[3];
    expect(added.content).toBe('补充决策：优先使用 Ed25519 签名');
    expect(added.isCustom).toBe(true);

    useHandoffBriefStore.getState().removeItem('session-prev-101', added.id);
    expect(useHandoffBriefStore.getState().briefs['session-prev-101'].items).toHaveLength(3);
  });

  it('builds structured handoff context prompt excluding disabled items', () => {
    const prompt = buildHandoffContextPrompt(mockBrief, '请先编写单测');
    expect(prompt).toContain('来源会话：重构认证服务与 Token 刷新');
    expect(prompt).toContain('【核心架构决策】');
    expect(prompt).toContain('采用双 Token 架构');
    expect(prompt).toContain('【待办与下一步任务】');
    expect(prompt).toContain('对接 Redis 黑名单失效逻辑');
    expect(prompt).toContain('【关键约束与规范】');
    expect(prompt).toContain('【用户额外补充要求】');
    expect(prompt).toContain('请先编写单测');
  });
});
