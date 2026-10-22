import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import ToneDraftApprovalCard from '../ToneDraftApprovalCard';
import type { DigitalSelfDraftItem } from '../digitalSelfTypes';

const mockDraft: DigitalSelfDraftItem = {
  id: 'draft_test_123',
  channel: 'feishu',
  recipientName: '王总 (产品总监)',
  relationship: 'leader',
  toneStyle: 'formal',
  originalMessage: '明天的技术选型会准备好了吗？',
  originalTimestamp: Date.now() - 1800000,
  draftContent: '王总您好，材料已准备就绪，包含性能对比与成本测算，明早准时汇报。',
  contextSources: [
    { id: 'src_1', title: '选型方案 PPT', excerpt: '对比了 4 款主流架构' },
  ],
  status: 'pending_review',
  createdAt: Date.now(),
  explicitlyConfirmedByHuman: false,
};

describe('ToneDraftApprovalCard', () => {
  it('renders outbound hard-gate safety banner and recipient metadata', () => {
    const onConfirmSend = vi.fn();
    const onDiscard = vi.fn();
    const onUpdateContent = vi.fn();
    const onChangeTone = vi.fn();

    render(
      <ToneDraftApprovalCard
        draft={mockDraft}
        onConfirmSend={onConfirmSend}
        onDiscard={onDiscard}
        onUpdateContent={onUpdateContent}
        onChangeTone={onChangeTone}
      />,
    );

    expect(screen.getByTestId('outbound-hard-gate-banner')).toBeDefined();
    expect(screen.getByText(/出站发送物理安全门禁/)).toBeDefined();
    expect(screen.getByText('飞书')).toBeDefined();
    expect(screen.getByText('王总 (产品总监)')).toBeDefined();
    expect(screen.getByText('直属领导')).toBeDefined();
    expect(screen.getByText(/明天的技术选型会准备好了吗/)).toBeDefined();
  });

  it('toggles reference context sources visibility', () => {
    const onConfirmSend = vi.fn();
    const onDiscard = vi.fn();
    const onUpdateContent = vi.fn();
    const onChangeTone = vi.fn();

    render(
      <ToneDraftApprovalCard
        draft={mockDraft}
        onConfirmSend={onConfirmSend}
        onDiscard={onDiscard}
        onUpdateContent={onUpdateContent}
        onChangeTone={onChangeTone}
      />,
    );

    expect(screen.queryByTestId('context-sources-list')).toBeNull();

    const toggleBtn = screen.getByTestId('toggle-sources-btn');
    fireEvent.click(toggleBtn);

    expect(screen.getByTestId('context-sources-list')).toBeDefined();
    expect(screen.getByText('选型方案 PPT')).toBeDefined();
  });

  it('allows inline editing of draft content', () => {
    const onConfirmSend = vi.fn();
    const onDiscard = vi.fn();
    const onUpdateContent = vi.fn();
    const onChangeTone = vi.fn();

    render(
      <ToneDraftApprovalCard
        draft={mockDraft}
        onConfirmSend={onConfirmSend}
        onDiscard={onDiscard}
        onUpdateContent={onUpdateContent}
        onChangeTone={onChangeTone}
      />,
    );

    const textarea = screen.getByTestId('draft-content-textarea') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: '修改后的草稿内容' } });

    expect(onUpdateContent).toHaveBeenCalledWith('draft_test_123', '修改后的草稿内容');
  });

  it('triggers discard when discard button is clicked', () => {
    const onConfirmSend = vi.fn();
    const onDiscard = vi.fn();
    const onUpdateContent = vi.fn();
    const onChangeTone = vi.fn();

    render(
      <ToneDraftApprovalCard
        draft={mockDraft}
        onConfirmSend={onConfirmSend}
        onDiscard={onDiscard}
        onUpdateContent={onUpdateContent}
        onChangeTone={onChangeTone}
      />,
    );

    const discardBtn = screen.getByTestId('discard-draft-btn');
    fireEvent.click(discardBtn);

    expect(onDiscard).toHaveBeenCalledWith('draft_test_123');
  });

  it('triggers explicit outbound confirmation when send button is clicked', async () => {
    const onConfirmSend = vi.fn();
    const onDiscard = vi.fn();
    const onUpdateContent = vi.fn();
    const onChangeTone = vi.fn();

    render(
      <ToneDraftApprovalCard
        draft={mockDraft}
        onConfirmSend={onConfirmSend}
        onDiscard={onDiscard}
        onUpdateContent={onUpdateContent}
        onChangeTone={onChangeTone}
      />,
    );

    const sendBtn = screen.getByTestId('confirm-send-btn');
    fireEvent.click(sendBtn);

    expect(onConfirmSend).toHaveBeenCalledWith('draft_test_123');
  });

  it('renders sent status and locks editing when draft is confirmed_sent', () => {
    const sentDraft: DigitalSelfDraftItem = {
      ...mockDraft,
      status: 'confirmed_sent',
      confirmedAt: Date.now(),
      explicitlyConfirmedByHuman: true,
    };

    render(
      <ToneDraftApprovalCard
        draft={sentDraft}
        onConfirmSend={vi.fn()}
        onDiscard={vi.fn()}
        onUpdateContent={vi.fn()}
        onChangeTone={vi.fn()}
      />,
    );

    expect(screen.getByTestId('sent-status-badge')).toBeDefined();
    expect(screen.queryByTestId('confirm-send-btn')).toBeNull();
    expect(screen.queryByTestId('discard-draft-btn')).toBeNull();

    const textarea = screen.getByTestId('draft-content-textarea') as HTMLTextAreaElement;
    expect(textarea.disabled).toBe(true);
  });
});
