import { describe, it, expect } from 'vitest';
import {
  evaluateRiskLevel,
  computeApprovalStats,
  applyApprovalDecision,
  DEFAULT_APPROVAL_REQUESTS,
} from '../executiveApprovalEngine';
import type { ApprovalRequest } from '../executiveApprovalTypes';

describe('executiveApprovalEngine', () => {
  it('默认审批列表中应包含不同风险等级与操作类型的完备场景', () => {
    expect(DEFAULT_APPROVAL_REQUESTS.length).toBeGreaterThanOrEqual(3);
    const hasPublish = DEFAULT_APPROVAL_REQUESTS.some((r) => {
      return r.actionType === 'publish';
    });
    const hasDelete = DEFAULT_APPROVAL_REQUESTS.some((r) => {
      return r.actionType === 'delete';
    });
    const hasPayment = DEFAULT_APPROVAL_REQUESTS.some((r) => {
      return r.actionType === 'payment';
    });

    expect(hasPublish).toBe(true);
    expect(hasDelete).toBe(true);
    expect(hasPayment).toBe(true);
  });

  describe('evaluateRiskLevel', () => {
    it('对转账与支付操作应判定为最高 critical 风险红线', () => {
      const res = evaluateRiskLevel('payment');
      expect(res.level).toBe('critical');
      expect(res.reason).toContain('财务转账与支付授权');
    });

    it('对删除、发布与部署操作应判定为 high 风险', () => {
      expect(evaluateRiskLevel('delete').level).toBe('high');
      expect(evaluateRiskLevel('publish').level).toBe('high');
      expect(evaluateRiskLevel('deploy').level).toBe('high');
    });

    it('对常规自定义操作应安全兜底为 low 风险', () => {
      const res = evaluateRiskLevel('custom');
      expect(res.level).toBe('low');
      expect(res.reason).toContain('沙箱隔离');
    });
  });

  describe('computeApprovalStats', () => {
    it('能正确聚合统计待批、已批准、已驳回与高危拦截工单数', () => {
      const mockRequests: ApprovalRequest[] = [
        {
          id: '1',
          taskId: 't1',
          agentId: 'a1',
          agentName: 'A1',
          actionType: 'payment',
          actionTitle: 'Pay',
          targetChannel: 'Bank',
          summary: 'sum',
          proposedContent: 'USD 100',
          riskLevel: 'critical',
          riskReason: 'money',
          createdAt: '2026-10-15T12:00:00Z',
          status: 'pending',
        },
        {
          id: '2',
          taskId: 't2',
          agentId: 'a2',
          agentName: 'A2',
          actionType: 'publish',
          actionTitle: 'Tweet',
          targetChannel: 'Weibo',
          summary: 'sum',
          proposedContent: 'Hello',
          riskLevel: 'high',
          riskReason: 'public',
          createdAt: '2026-10-15T12:00:00Z',
          status: 'approved',
        },
        {
          id: '3',
          taskId: 't3',
          agentId: 'a3',
          agentName: 'A3',
          actionType: 'custom',
          actionTitle: 'Clean',
          targetChannel: 'Local',
          summary: 'sum',
          proposedContent: 'echo 1',
          riskLevel: 'low',
          riskReason: 'safe',
          createdAt: '2026-10-15T12:00:00Z',
          status: 'rejected',
        },
      ];

      const stats = computeApprovalStats(mockRequests);
      expect(stats.totalCount).toBe(3);
      expect(stats.pendingCount).toBe(1);
      expect(stats.approvedCount).toBe(1);
      expect(stats.rejectedCount).toBe(1);
      expect(stats.highRiskCount).toBe(2);
    });
  });

  describe('applyApprovalDecision', () => {
    const baseRequest: ApprovalRequest = {
      id: 'r1',
      taskId: 't1',
      agentId: 'a1',
      agentName: 'Agent',
      actionType: 'publish',
      actionTitle: 'Publish Blog',
      targetChannel: 'Blog',
      summary: 'Summary',
      proposedContent: 'Original Content',
      riskLevel: 'high',
      riskReason: 'Public impact',
      createdAt: '2026-10-15T10:00:00Z',
      status: 'pending',
    };

    it('approve 决策应将状态更新为 approved', () => {
      const res = applyApprovalDecision(baseRequest, {
        decision: 'approve',
        feedbackComment: '准许发布',
      });
      expect(res.status).toBe('approved');
      expect(res.feedbackComment).toBe('准许发布');
    });

    it('reject 决策应将状态更新为 rejected 并保留驳回批注', () => {
      const res = applyApprovalDecision(baseRequest, {
        decision: 'reject',
        feedbackComment: '需要修改第二段内容',
      });
      expect(res.status).toBe('rejected');
      expect(res.feedbackComment).toBe('需要修改第二段内容');
    });

    it('modify_and_approve 决策应就地修改并批准', () => {
      const res = applyApprovalDecision(baseRequest, {
        decision: 'modify_and_approve',
        modifiedContent: 'Modified Content',
        feedbackComment: '董事长微调后放行',
      });
      expect(res.status).toBe('modified_approved');
      expect(res.modifiedContent).toBe('Modified Content');
      expect(res.feedbackComment).toBe('董事长微调后放行');
    });
  });
});
