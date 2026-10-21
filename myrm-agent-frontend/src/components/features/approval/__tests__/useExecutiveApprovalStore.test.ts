import { describe, it, expect, beforeEach } from 'vitest';
import { useExecutiveApprovalStore } from '../useExecutiveApprovalStore';

describe('useExecutiveApprovalStore', () => {
  beforeEach(() => {
    useExecutiveApprovalStore.getState().resetStore();
  });

  it('初始状态应加载默认待审批工单池', () => {
    const state = useExecutiveApprovalStore.getState();
    expect(state.requests.length).toBeGreaterThan(0);
    expect(state.filterStatus).toBe('pending');
    expect(state.filterRiskLevel).toBe('all');
    expect(state.isDeckOpen).toBe(false);
  });

  it('submitApprovalRequest 能成功新建待审工单并自动选中', () => {
    const store = useExecutiveApprovalStore.getState();
    const newId = store.submitApprovalRequest({
      taskId: 'task-test-999',
      agentId: 'agent-bot',
      agentName: '测试分身',
      actionType: 'deploy',
      actionTitle: '发布灰度集群',
      targetChannel: 'K8s cluster',
      summary: '自动化打包完成，请求滚动更新',
      proposedContent: 'kubectl rollout restart deployment',
      riskLevel: 'high',
      riskReason: '灰度更新现网服务',
    });

    const state = useExecutiveApprovalStore.getState();
    expect(state.selectedRequestId).toBe(newId);
    const found = state.requests.find((r) => {
      return r.id === newId;
    });
    expect(found).toBeDefined();
    if (found) {
      expect(found.status).toBe('pending');
      expect(found.actionType).toBe('deploy');
    }
  });

  it('approveRequest 能将对应工单流转为 approved 态', () => {
    const store = useExecutiveApprovalStore.getState();
    const first = store.requests[0];
    expect(first).toBeDefined();
    if (first) {
      store.approveRequest(first.id, '符合上线规范，准许执行');
      const updated = useExecutiveApprovalStore.getState().requests.find((r) => {
        return r.id === first.id;
      });
      expect(updated?.status).toBe('approved');
      expect(updated?.feedbackComment).toBe('符合上线规范，准许执行');
    }
  });

  it('rejectRequest 能将对应工单流转为 rejected 态并记录驳回反馈', () => {
    const store = useExecutiveApprovalStore.getState();
    const first = store.requests[0];
    expect(first).toBeDefined();
    if (first) {
      store.rejectRequest(first.id, '参数存在漏洞，请核实后重提');
      const updated = useExecutiveApprovalStore.getState().requests.find((r) => {
        return r.id === first.id;
      });
      expect(updated?.status).toBe('rejected');
      expect(updated?.feedbackComment).toBe('参数存在漏洞，请核实后重提');
    }
  });

  it('modifyAndApproveRequest 能现场修改参数并批准流转', () => {
    const store = useExecutiveApprovalStore.getState();
    const first = store.requests[0];
    expect(first).toBeDefined();
    if (first) {
      store.modifyAndApproveRequest(first.id, '安全修改后的执行指令', '已人工加固');
      const updated = useExecutiveApprovalStore.getState().requests.find((r) => {
        return r.id === first.id;
      });
      expect(updated?.status).toBe('modified_approved');
      expect(updated?.modifiedContent).toBe('安全修改后的执行指令');
      expect(updated?.feedbackComment).toBe('已人工加固');
    }
  });

  it('过滤器与弹窗开关状态更新正常', () => {
    const store = useExecutiveApprovalStore.getState();
    store.setRiskFilter('critical');
    expect(useExecutiveApprovalStore.getState().filterRiskLevel).toBe('critical');

    store.setStatusFilter('approved');
    expect(useExecutiveApprovalStore.getState().filterStatus).toBe('approved');

    store.toggleDeck(true);
    expect(useExecutiveApprovalStore.getState().isDeckOpen).toBe(true);

    store.toggleDeck();
    expect(useExecutiveApprovalStore.getState().isDeckOpen).toBe(false);
  });
});
