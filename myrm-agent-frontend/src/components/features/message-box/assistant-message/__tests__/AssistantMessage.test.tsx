import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import { AssistantMessage } from '../AssistantMessage';

const stableT = (key: string) => key;

const storeState = vi.hoisted(() => ({
  messages: [] as unknown[],
  approvalQueue: [] as Array<{ messageId: string }>,
  config: {
    enableEvalLab: false,
    reasoningDisplayMode: 'collapsed',
    personalSettings: {} as { reasoningDisplayMode?: string },
  },
}));

type Props = Record<string, unknown>;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({ messages: storeState.messages, workspaceDir: '/workspace' }),
}));
vi.mock('@/store/useToolApprovalStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) => selector({ queue: storeState.approvalQueue }),
}));
vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) => selector(storeState.config),
}));
vi.mock('@/components/features/message-box/assistant-message/useAssistantMessageActions', () => ({
  useAssistantMessageActions: () => ({ handleRegenerate: vi.fn(), handleCancel: vi.fn() }),
}));
vi.mock('@/components/features/message-box/assistant-message/AssistantRunOutputs', () => ({
  AssistantRunOutputs: (props: Props) => (
    <div data-testid="run-outputs" data-approval={String(props.approvalPending)} data-chat={String(props.chatId)} />
  ),
}));
vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: (props: Props) => (
    <div
      data-testid="markdown"
      data-streaming={String(props.isStreaming)}
      data-workspace={String(props.workspaceDir)}
      data-chat={String(props.chatId)}
    >
      {String(props.content)}
    </div>
  ),
}));
vi.mock('@/components/features/message-box/MessageActionBar', () => ({
  default: (props: Props) => (
    <div data-testid="action-bar" data-eval-lab={String(props.enableEvalLab)} data-chat={String(props.chatId)} />
  ),
}));
vi.mock('@/components/features/message-box/ReasoningProcessAccordion', () => ({
  default: (props: Props) => <div data-testid="reasoning" data-mode={String(props.displayMode)} />,
}));
vi.mock('@/components/features/message-box/QuoteToolbar', () => ({
  QuoteToolbar: () => <div data-testid="quote-toolbar" />,
  useQuoteSelection: () => ({ state: null, dismiss: vi.fn() }),
}));
vi.mock('@/components/features/message-box/ClarificationInput', () => ({
  default: () => <div data-testid="clarification" />,
}));
vi.mock('@/components/features/message-box/DeliverableTierBadge', () => ({
  DeliverableTierBadge: () => <div data-testid="tier" />,
}));
vi.mock('@/components/features/message-box/FileMutationWarning', () => ({
  FileMutationWarning: () => <div data-testid="file-warning" />,
}));
vi.mock('@/components/features/message-box/HumanGateCard', () => ({
  HumanGateCard: () => <div data-testid="human-gate" />,
}));
vi.mock('@/components/features/message-box/MemoryInsightPanel', () => ({
  default: () => <div data-testid="memory" />,
}));
vi.mock('@/components/features/message-box/MessageToc', () => ({ MessageToc: () => <div data-testid="toc" /> }));
vi.mock('@/components/features/message-box/ModelSpecialtyChip', () => ({
  ModelSpecialtyChip: () => <div data-testid="specialty" />,
}));
vi.mock('@/components/features/message-box/PlanConfirmationCard', () => ({
  default: () => <div data-testid="plan" />,
}));
vi.mock('@/components/features/message-box/StagedArtifactsNotice', () => ({
  StagedArtifactsNotice: () => <div data-testid="staged" />,
}));
vi.mock('@/components/features/message-box/Suggestions', () => ({ default: () => <div data-testid="suggestions" /> }));
vi.mock('@/components/features/message-box/WaitingTtftIndicator', () => ({
  default: () => <div data-testid="ttft" />,
}));
vi.mock('@/components/features/message-box/WaterDropCostView', () => ({ default: () => <div data-testid="cost" /> }));
vi.mock('@/components/features/message-box/WorkflowSuggestionCard', () => ({
  default: () => <div data-testid="workflow-suggestion" />,
}));
vi.mock('@/components/features/message-box/WorkflowTemplateSaveCard', () => ({
  default: () => <div data-testid="template-save" />,
}));

function message(extra: Partial<Message> = {}): Message {
  return {
    messageId: 'a1',
    chatId: 'chat-1',
    role: 'assistant',
    content: 'answer text',
    createdAt: new Date('2026-11-09T00:00:00.000Z'),
    ...extra,
  };
}

function renderBubble(extra: Partial<Message> = {}, props: Partial<Parameters<typeof AssistantMessage>[0]> = {}) {
  const target = message(extra);
  storeState.messages = [target];
  return render(
    <AssistantMessage message={target} messageIndex={0} loading={false} isLast={false} chatId="chat-1" {...props} />,
  );
}

const STREAMING = { loading: true, isLast: true };

describe('AssistantMessage', () => {
  beforeEach(() => {
    storeState.messages = [];
    storeState.approvalQueue = [];
    storeState.config = { enableEvalLab: false, reasoningDisplayMode: 'collapsed', personalSettings: {} };
  });

  it('shows the run outputs above the answer block', () => {
    const { container } = renderBubble();

    expect(container.querySelector('[data-test-id="assistant-message"]')).not.toBeNull();
    expect(screen.getByText('answer')).toBeTruthy();
    expect(screen.getByTestId('markdown').textContent).toBe('answer text');
    expect(
      screen.getByTestId('run-outputs').compareDocumentPosition(screen.getByTestId('markdown')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('closes a reasoning tag the stream has not closed yet before rendering the text', () => {
    renderBubble({ content: 'before <think>still thinking' });

    expect(screen.getByTestId('markdown').textContent).toBe('before <think>still thinking</think> <a> </a>');
  });

  it('tells the markdown whether the answer is still streaming', () => {
    const { unmount } = renderBubble({}, STREAMING);
    expect(screen.getByTestId('markdown').getAttribute('data-streaming')).toBe('true');
    unmount();

    renderBubble({}, { loading: true, isLast: false });
    expect(screen.getByTestId('markdown').getAttribute('data-streaming')).toBe('false');
  });

  it('shows the specialty chip, the plan, the human gate and the workflow suggestion only when the message has them', () => {
    const { unmount } = renderBubble();
    for (const testId of ['specialty', 'plan', 'human-gate', 'workflow-suggestion']) {
      expect(screen.queryByTestId(testId)).toBeNull();
    }
    unmount();

    renderBubble({
      routingSpecialty: 'code',
      planConfirmation: { plan: 'p', status: 'waiting' } as unknown as Message['planConfirmation'],
      humanGate: { question: 'q', options: [], status: 'waiting' } as unknown as Message['humanGate'],
      workflowSuggestion: { status: 'suggested' } as unknown as Message['workflowSuggestion'],
    });
    for (const testId of ['specialty', 'plan', 'human-gate', 'workflow-suggestion']) {
      expect(screen.getByTestId(testId)).toBeTruthy();
    }
  });

  it.each([
    ['an async task', '{"task_id":"t1"}'],
    ['a text-to-speech result', '{"status":"success","audio_url":"/a.mp3"}'],
  ])('leaves the answer block out when the reply is %s', (_label, content) => {
    renderBubble({ content });

    expect(screen.getByTestId('run-outputs')).toBeTruthy();
    expect(screen.queryByText('answer')).toBeNull();
    expect(screen.queryByTestId('markdown')).toBeNull();
    expect(screen.queryByTestId('action-bar')).toBeNull();
  });

  it('tells the run outputs whether an approval is waiting on this message only', () => {
    storeState.approvalQueue = [{ messageId: 'other' }];
    const { unmount } = renderBubble();
    expect(screen.getByTestId('run-outputs').getAttribute('data-approval')).toBe('false');
    unmount();

    storeState.approvalQueue = [{ messageId: 'a1' }];
    renderBubble();
    expect(screen.getByTestId('run-outputs').getAttribute('data-approval')).toBe('true');
  });

  it('hands the open chat, the workspace and the eval-lab switch to the parts that need them', () => {
    storeState.config = { ...storeState.config, enableEvalLab: true };
    renderBubble();

    expect(screen.getByTestId('run-outputs').getAttribute('data-chat')).toBe('chat-1');
    expect(screen.getByTestId('markdown').getAttribute('data-chat')).toBe('chat-1');
    expect(screen.getByTestId('markdown').getAttribute('data-workspace')).toBe('/workspace');
    expect(screen.getByTestId('action-bar').getAttribute('data-chat')).toBe('chat-1');
    expect(screen.getByTestId('action-bar').getAttribute('data-eval-lab')).toBe('true');
  });

  it.each([
    ['collapsed', {}, true],
    ['inline', {}, true],
    ['off', {}, false],
    ['collapsed', { reasoningDisplayMode: 'off' }, false],
    ['off', { reasoningDisplayMode: 'inline' }, true],
  ])('with the global mode %s and the personal setting %j the reasoning block shows: %s', (mode, personal, shown) => {
    storeState.config = { enableEvalLab: false, reasoningDisplayMode: mode, personalSettings: personal };
    renderBubble({ reasoning: 'thinking' });

    expect(screen.queryByTestId('reasoning') !== null).toBe(shown);
  });

  it('shows no reasoning block for a message without reasoning', () => {
    renderBubble();

    expect(screen.queryByTestId('reasoning')).toBeNull();
  });

  it.each([
    ['no text and no reasoning yet', {}, 'collapsed', STREAMING, true],
    ['text', { content: 'hello' }, 'collapsed', STREAMING, false],
    ['reasoning that is shown', { content: '', reasoning: 'thinking' }, 'collapsed', STREAMING, false],
    ['reasoning that is switched off', { content: '', reasoning: 'thinking' }, 'off', STREAMING, true],
    ['no text, but not streaming', { content: '' }, 'collapsed', { loading: false, isLast: true }, false],
    ['no text, in an earlier answer', { content: '' }, 'collapsed', { loading: true, isLast: false }, false],
  ] as const)('first-token indicator with %s: %s', (_label, extra, mode, state, shown) => {
    storeState.config = { enableEvalLab: false, reasoningDisplayMode: mode, personalSettings: {} };
    renderBubble({ content: '', ...extra }, state);

    expect(screen.queryByTestId('ttft') !== null).toBe(shown);
  });

  it('keeps the inline clarification unless the composer has taken it over', () => {
    const asking = message({ clarification: { answered: false, options: ['a'] } });
    storeState.messages = [asking];
    const { unmount } = render(
      <AssistantMessage message={asking} messageIndex={0} loading={false} isLast chatId="chat-1" />,
    );
    expect(screen.queryByTestId('clarification')).toBeNull();
    unmount();

    const answered = message({ messageId: 'a2', clarification: { answered: true, options: ['a'] } });
    storeState.messages = [asking, answered];
    render(<AssistantMessage message={answered} messageIndex={1} loading={false} isLast chatId="chat-1" />);
    expect(screen.getByTestId('clarification')).toBeTruthy();
  });

  it.each([
    ['finished', { loading: false, isLast: true }, 'chat-1', true],
    ['an earlier answer while another streams', { loading: true, isLast: false }, 'chat-1', true],
    ['streaming', STREAMING, 'chat-1', false],
    ['finished without an open chat', { loading: false, isLast: true }, undefined, false],
  ] as const)('workflow template save card when %s: %s', (_label, state, chatId, shown) => {
    renderBubble({}, { ...state, chatId });

    expect(screen.queryByTestId('template-save') !== null).toBe(shown);
  });

  it('offers suggestions on the latest answer only', () => {
    const { unmount } = renderBubble({}, { isLast: true });
    expect(screen.getByTestId('suggestions')).toBeTruthy();
    unmount();

    renderBubble({}, { isLast: false });
    expect(screen.queryByTestId('suggestions')).toBeNull();
  });

  it('holds back the tier badge and the failure notices until the answer is done', () => {
    const extra: Partial<Message> = {
      deliverableTier: { tier: 'VERIFIED' } as unknown as Message['deliverableTier'],
      fileMutationFailures: [{ path: 'a.txt', error: 'x' }] as unknown as Message['fileMutationFailures'],
      stagedArtifacts: [{ id: 's1' }] as unknown as Message['stagedArtifacts'],
    };
    const { unmount } = renderBubble(extra, STREAMING);
    for (const testId of ['tier', 'file-warning', 'staged']) {
      expect(screen.queryByTestId(testId)).toBeNull();
    }
    unmount();

    renderBubble(extra);
    for (const testId of ['tier', 'file-warning', 'staged']) {
      expect(screen.getByTestId(testId)).toBeTruthy();
    }
  });

  it('shows the banner of an abnormal ending once the answer is done, not while it streams', () => {
    const { unmount } = renderBubble({ completionStatus: 'truncated' }, STREAMING);
    expect(screen.queryByText('message.truncated')).toBeNull();
    unmount();

    renderBubble({ completionStatus: 'truncated' });
    expect(screen.getByText('message.truncated')).toBeTruthy();
  });

  it('shows the streaming dots after the first text, and neither dots nor opacity while it fades out', () => {
    const { container, unmount } = renderBubble({}, STREAMING);
    expect(container.querySelector('[aria-label="Loading"]')).not.toBeNull();
    expect(screen.getByTestId('markdown').parentElement?.className).toContain('opacity-100');
    unmount();

    const faded = renderBubble({ isFadingOut: true }, STREAMING);
    expect(faded.container.querySelector('[aria-label="Loading"]')).toBeNull();
    expect(screen.getByTestId('markdown').parentElement?.className).toContain('opacity-0');
  });

  it.each([
    ['generating the answer', [{ step_key: 'searching' }, { step_key: 'Generating' }], true],
    ['writing the answer', [{ step_key: 'final_ANSWER' }], true],
    ['searching', [{ step_key: 'generating' }, { step_key: 'searching' }], false],
    ['no steps', [], false],
  ])('spins the answer icon only while the last step is %s and the answer streams', (_label, steps, spins) => {
    const { container } = renderBubble({ progressSteps: steps }, STREAMING);

    expect(container.querySelector('svg')?.getAttribute('class')?.includes('animate-spin')).toBe(spins);
  });

  it('keeps the answer icon still when the answer is not streaming', () => {
    const { container } = renderBubble({ progressSteps: [{ step_key: 'generating_answer' }] });

    expect(container.querySelector('svg')?.getAttribute('class')).toContain('animate-none');
  });
});
