import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useDigitalSelfDraftStore } from '../useDigitalSelfDraftStore';

describe('useDigitalSelfDraftStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useDigitalSelfDraftStore.setState({ drafts: [], auditLog: [] });
  });

  it('adds a new draft with pending_review status and unconfirmed gate', () => {
    const { addDraft } = useDigitalSelfDraftStore.getState();

    const draftId = addDraft({
      channel: 'feishu',
      recipientName: '张总 (技术VP)',
      relationship: 'leader',
      toneStyle: 'formal',
      originalMessage: '下周的架构重构评审材料准备得怎么样了？',
      originalTimestamp: Date.now() - 3600000,
      draftContent: '张总您好，架构重构方案已完成初稿，已同步至评审群，请您审阅。',
      contextSources: [
        { id: 's1', title: 'Roadmap 文档', excerpt: '已完成 81 项' },
      ],
    });

    const state = useDigitalSelfDraftStore.getState();
    expect(state.drafts).toHaveLength(1);
    expect(state.drafts[0].id).toBe(draftId);
    expect(state.drafts[0].status).toBe('pending_review');
    expect(state.drafts[0].explicitlyConfirmedByHuman).toBe(false);
  });

  it('updates draft content and marks status as edited', () => {
    const { addDraft, updateDraftContent } = useDigitalSelfDraftStore.getState();
    const draftId = addDraft({
      channel: 'email',
      recipientName: '李经理',
      relationship: 'partner',
      toneStyle: 'semi-formal',
      originalMessage: '合同样本请过目',
      originalTimestamp: Date.now(),
      draftContent: '收到，正在法务复核。',
      contextSources: [],
    });

    updateDraftContent(draftId, '收到，已移交法务加急审查，预计今日下班前反馈。');

    const draft = useDigitalSelfDraftStore.getState().drafts[0];
    expect(draft.draftContent).toBe('收到，已移交法务加急审查，预计今日下班前反馈。');
    expect(draft.status).toBe('edited');
  });

  it('switches tone style on draft', () => {
    const { addDraft, changeToneStyle } = useDigitalSelfDraftStore.getState();
    const draftId = addDraft({
      channel: 'dingtalk',
      recipientName: '小王',
      relationship: 'teammate',
      toneStyle: 'formal',
      originalMessage: 'PR 帮我看一下',
      originalTimestamp: Date.now(),
      draftContent: '好的，稍后为您处理。',
      contextSources: [],
    });

    changeToneStyle(draftId, 'friendly');

    const draft = useDigitalSelfDraftStore.getState().drafts[0];
    expect(draft.toneStyle).toBe('friendly');
  });

  it('enforces physical outbound hard-gate upon explicit human confirmation', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const { addDraft, confirmAndSendOutbound } = useDigitalSelfDraftStore.getState();

    const draftId = addDraft({
      channel: 'feishu',
      recipientName: '王总',
      relationship: 'leader',
      toneStyle: 'formal',
      originalMessage: '请确认进度',
      originalTimestamp: Date.now(),
      draftContent: '方案已备妥，请审阅。',
      contextSources: [],
    });

    const res = await confirmAndSendOutbound(draftId);
    expect(res.success).toBe(true);

    const state = useDigitalSelfDraftStore.getState();
    const draft = state.drafts[0];
    expect(draft.status).toBe('confirmed_sent');
    expect(draft.explicitlyConfirmedByHuman).toBe(true);
    expect(draft.confirmedAt).toBeDefined();

    // Audit log recorded
    expect(state.auditLog).toHaveLength(1);
    expect(state.auditLog[0].draftId).toBe(draftId);
    expect(state.auditLog[0].confirmedByHuman).toBe(true);

    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(CustomEvent));
  });

  it('discards a draft and clears completed', () => {
    const { addDraft, discardDraft, clearCompleted } = useDigitalSelfDraftStore.getState();
    const draftId = addDraft({
      channel: 'wechat',
      recipientName: '客户陈经理',
      relationship: 'partner',
      toneStyle: 'formal',
      originalMessage: '今天能碰一下吗？',
      originalTimestamp: Date.now(),
      draftContent: '好的',
      contextSources: [],
    });

    discardDraft(draftId);
    expect(useDigitalSelfDraftStore.getState().drafts[0].status).toBe('discarded');

    clearCompleted();
    expect(useDigitalSelfDraftStore.getState().drafts).toHaveLength(0);
  });
});
