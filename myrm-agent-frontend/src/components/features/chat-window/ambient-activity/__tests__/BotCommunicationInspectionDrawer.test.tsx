import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BotCommunicationInspectionDrawer } from '../BotCommunicationInspectionDrawer';
import { useAmbientActivityStore } from '../useAmbientActivityStore';

describe('BotCommunicationInspectionDrawer', () => {
  beforeEach(() => {
    useAmbientActivityStore.getState().reset();
  });

  it('renders nothing when drawer is closed', () => {
    const { container } = render(<BotCommunicationInspectionDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer with communication metadata and payload when open', () => {
    useAmbientActivityStore.getState().recordActivity({
      id: 'act-audit-1',
      sessionId: 'session-audit-xyz',
      sourceAgent: 'LegalCounsel',
      targetAgent: 'ProjectLead',
      actionSummary: '法务审查合规盖章',
      payloadSnippet: '{"approved": true, "clause": 12}',
      tokenCost: 180,
      latencyMs: 95,
      status: 'completed',
    });

    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    render(<BotCommunicationInspectionDrawer />);

    expect(screen.getByTestId('bot-inspection-drawer')).toBeDefined();
    expect(screen.getByText('机器协同通信信封深度审计')).toBeDefined();
    expect(screen.getByText('耗时: 95ms')).toBeDefined();
    expect(screen.getByText('Token 消耗: 180 tok')).toBeDefined();
    expect(screen.getByText('状态: completed')).toBeDefined();
    expect(screen.getByText(/session-audit-xyz/)).toBeDefined();
    expect(screen.getByText('法务审查合规盖章')).toBeDefined();
    expect(
      screen.getByText('{"approved": true, "clause": 12}'),
    ).toBeDefined();
  });

  it('supports copying payload snippet to clipboard', () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockImplementation(() => Promise.resolve()),
      },
    });

    useAmbientActivityStore.getState().recordActivity({
      id: 'act-copy-1',
      sessionId: 'sess-copy',
      sourceAgent: 'Agent1',
      targetAgent: 'Agent2',
      actionSummary: '测试复制',
      payloadSnippet: 'payload-to-copy-string',
      tokenCost: 10,
      latencyMs: 5,
      status: 'completed',
    });

    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    render(<BotCommunicationInspectionDrawer />);

    const copyBtn = screen.getByLabelText('复制信封报文');
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      'payload-to-copy-string',
    );
  });

  it('allows switching selected activity', () => {
    useAmbientActivityStore.getState().recordActivity({
      id: 'act-first',
      sessionId: 'sess-1',
      sourceAgent: 'Bot1',
      targetAgent: 'Bot2',
      actionSummary: '第一个动作',
      payloadSnippet: 'content-1',
      tokenCost: 10,
      latencyMs: 5,
      status: 'completed',
    });
    useAmbientActivityStore.getState().recordActivity({
      id: 'act-second',
      sessionId: 'sess-2',
      sourceAgent: 'Bot3',
      targetAgent: 'Bot4',
      actionSummary: '第二个动作',
      payloadSnippet: 'content-2',
      tokenCost: 20,
      latencyMs: 15,
      status: 'completed',
    });

    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    render(<BotCommunicationInspectionDrawer />);

    const switchBtn = screen.getByText('@Bot1 ➔ @Bot2');
    fireEvent.click(switchBtn);

    expect(screen.getByText('第一个动作')).toBeDefined();
    expect(screen.getByText('content-1')).toBeDefined();
  });

  it('closes drawer when close button is clicked', () => {
    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    render(<BotCommunicationInspectionDrawer />);

    const closeBtn = screen.getByLabelText('关闭审计抽屉');
    fireEvent.click(closeBtn);

    expect(
      useAmbientActivityStore.getState().isInspectionDrawerOpen,
    ).toBe(false);
  });

  it('closes drawer when Escape key is pressed', () => {
    useAmbientActivityStore.getState().toggleInspectionDrawer(true);
    render(<BotCommunicationInspectionDrawer />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(
      useAmbientActivityStore.getState().isInspectionDrawerOpen,
    ).toBe(false);
  });
});
