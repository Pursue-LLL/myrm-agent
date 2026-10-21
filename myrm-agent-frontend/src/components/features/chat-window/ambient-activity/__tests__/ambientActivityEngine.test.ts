import { describe, expect, it } from 'vitest';
import {
  aggregateAmbientActivities,
  filterVisibleConversations,
  formatMicroActivitySummary,
} from '../ambientActivityEngine';
import {
  BotActivityItem,
  ConversationWithVisibility,
} from '../ambientActivityTypes';

describe('ambientActivityEngine', () => {
  describe('filterVisibleConversations', () => {
    const mockConversations: ConversationWithVisibility[] = [
      {
        id: 'conv-1',
        title: '用户主对话：发票整理',
        visibilityScope: 'human_visible',
      },
      {
        id: 'conv-2',
        title: 'Bot 间数据对齐通道',
        visibilityScope: 'hidden_bot_peer',
      },
      {
        id: 'conv-3',
        title: '未显式指定 scope 对话',
      },
    ];

    it('filters out hidden_bot_peer by default to protect human attention', () => {
      const visible = filterVisibleConversations(mockConversations);
      expect(visible).toHaveLength(2);
      expect(visible.map((c) => c.id)).toEqual(['conv-1', 'conv-3']);
    });

    it('retains all conversations when showHiddenBots is true', () => {
      const all = filterVisibleConversations(mockConversations, true);
      expect(all).toHaveLength(3);
      expect(all.map((c) => c.id)).toEqual(['conv-1', 'conv-2', 'conv-3']);
    });
  });

  describe('aggregateAmbientActivities', () => {
    it('returns empty summary for empty list', () => {
      const summary = aggregateAmbientActivities([]);
      expect(summary.activeAgentsCount).toBe(0);
      expect(summary.totalExchangesCount).toBe(0);
      expect(summary.totalTokenCost).toBe(0);
      expect(summary.recentHighlights).toEqual([]);
    });

    it('aggregates unique agents, total tokens, and top highlights', () => {
      const mockActivities: BotActivityItem[] = [
        {
          id: 'act-1',
          sessionId: 'sess-1',
          sourceAgent: '架构师',
          targetAgent: '安全审计员',
          actionSummary: '提交安全审计信封',
          payloadSnippet: '{}',
          tokenCost: 150,
          latencyMs: 80,
          timestamp: 1000,
          status: 'completed',
        },
        {
          id: 'act-2',
          sessionId: 'sess-1',
          sourceAgent: '安全审计员',
          targetAgent: '架构师',
          actionSummary: '返回合规签名',
          payloadSnippet: '{}',
          tokenCost: 200,
          latencyMs: 120,
          timestamp: 2000,
          status: 'completed',
        },
        {
          id: 'act-3',
          sessionId: 'sess-2',
          sourceAgent: '测试员',
          targetAgent: '架构师',
          actionSummary: '报告单测执行全绿',
          payloadSnippet: '{}',
          tokenCost: 100,
          latencyMs: 50,
          timestamp: 3000,
          status: 'completed',
        },
      ];

      const summary = aggregateAmbientActivities(mockActivities);
      expect(summary.activeAgentsCount).toBe(3); // 架构师, 安全审计员, 测试员
      expect(summary.totalExchangesCount).toBe(3);
      expect(summary.totalTokenCost).toBe(450);
      expect(summary.recentHighlights).toHaveLength(3);
      // 倒序排列：第1项应是 timestamp 3000 的 act-3
      expect(summary.recentHighlights[0]).toContain('@架构师: 报告单测执行全绿');
    });
  });

  describe('formatMicroActivitySummary', () => {
    it('formats single line micro activity with latency', () => {
      const item: BotActivityItem = {
        id: 'act-test',
        sessionId: 'sess-test',
        sourceAgent: 'CodeArchitect',
        targetAgent: 'LinterGuard',
        actionSummary: '校验代码风格',
        payloadSnippet: '{"rule": "pep8"}',
        tokenCost: 50,
        latencyMs: 120,
        timestamp: Date.now(),
        status: 'completed',
      };

      const formatted = formatMicroActivitySummary(item);
      expect(formatted).toBe('[@CodeArchitect -> @LinterGuard] 校验代码风格 (120ms)');
    });

    it('falls back to default labels when agents or latency are missing', () => {
      const item: BotActivityItem = {
        id: 'act-minimal',
        sessionId: 'sess-min',
        sourceAgent: '',
        targetAgent: '',
        actionSummary: '',
        payloadSnippet: '',
        tokenCost: 0,
        latencyMs: 0,
        timestamp: Date.now(),
        status: 'in_progress',
      };

      const formatted = formatMicroActivitySummary(item);
      expect(formatted).toBe('[@Agent -> @Agent] 同步协作数据');
    });
  });
});
