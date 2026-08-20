import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * WorkflowSuggestionCard 通过 useChatStore.setState 修改对应 assistant 消息的
 * workflowSuggestion.status。此处 mock store 为可变状态，真实还原 setState 应用
 * updater 的行为（与 immer 中间件语义一致），以验证 find+可选链 更新逻辑。
 */
const mockState = vi.hoisted(() => ({
  messages: [] as Array<{
    messageId: string;
    role: 'assistant' | 'user' | 'system';
    workflowSuggestion?: { status: 'suggested' | 'accepted' | 'dismissed' };
  }>,
  isWorkflowMode: false,
  setIsWorkflowMode: (v: boolean) => {
    mockState.isWorkflowMode = v;
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: typeof mockState) => unknown) => selector(mockState),
    {
      getState: () => mockState,
      setState: (updater: (state: typeof mockState) => void) => {
        // immer 语义：传入 updater 函数，draft 可原地修改
        updater(mockState);
      },
    },
  ),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconWorkflow: ({ className }: { className?: string }) => (
    <svg data-testid="icon-workflow" className={className} />
  ),
}));

import WorkflowSuggestionCard from '../WorkflowSuggestionCard';

const makeMessage = (messageId: string) => ({
  messageId,
  role: 'assistant' as const,
  workflowSuggestion: { status: 'suggested' as const },
});

describe('WorkflowSuggestionCard', () => {
  beforeEach(() => {
    mockState.messages = [makeMessage('msg-1')];
    mockState.isWorkflowMode = false;
  });

  it('renders nothing when dismissed', () => {
    render(<WorkflowSuggestionCard messageId="msg-1" status="dismissed" />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('activates workflow: sets suggestion to accepted and turns on workflow mode', async () => {
    const user = userEvent.setup();
    render(<WorkflowSuggestionCard messageId="msg-1" status="suggested" />);
    await user.click(screen.getByRole('button', { name: /activate/ }));

    expect(mockState.messages[0].workflowSuggestion?.status).toBe('accepted');
    expect(mockState.isWorkflowMode).toBe(true);
  });

  it('dismisses: sets suggestion to dismissed and does not turn on workflow', async () => {
    const user = userEvent.setup();
    render(<WorkflowSuggestionCard messageId="msg-1" status="suggested" />);
    await user.click(screen.getByRole('button', { name: /dismiss/ }));

    expect(mockState.messages[0].workflowSuggestion?.status).toBe('dismissed');
    expect(mockState.isWorkflowMode).toBe(false);
  });

  it('does not mutate any message when messageId not found', async () => {
    const user = userEvent.setup();
    render(<WorkflowSuggestionCard messageId="missing-id" status="suggested" />);
    await user.click(screen.getByRole('button', { name: /activate/ }));

    // 找不到目标消息时，不应修改任何消息，且仍开启 workflow 模式
    expect(mockState.messages[0].workflowSuggestion?.status).toBe('suggested');
    expect(mockState.isWorkflowMode).toBe(true);
  });

  it('does not mutate when the matched assistant message has no workflowSuggestion', async () => {
    mockState.messages = [{ messageId: 'msg-2', role: 'assistant' as const }];
    const user = userEvent.setup();
    render(<WorkflowSuggestionCard messageId="msg-2" status="suggested" />);
    await user.click(screen.getByRole('button', { name: /activate/ }));

    // 消息存在但无 workflowSuggestion 字段，不应 crash，也不该新增字段
    expect('workflowSuggestion' in mockState.messages[0]).toBe(false);
  });
});
