/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { RewindDialog } from '../RewindDialog';

const { toastMock, rewindToMessageMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  rewindToMessageMock: vi.fn(),
}));

const fetchPlanMock = vi.fn(async (_chatId: string): Promise<void> => undefined);

const stableT = (key: string, values?: Record<string, string | number>): string =>
  values?.count !== undefined ? `${key}:${String(values.count)}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    rewindToMessage: (...args: unknown[]) => rewindToMessageMock(...args),
  };
});

const makeMessage = (id: string, role: Message['role']): Message => ({
  messageId: id,
  chatId: 'c1',
  createdAt: new Date(),
  content: '',
  role,
});

const renderDialog = (messageIndex = 2, messageId = 'u2') => {
  const onOpenChange = vi.fn();
  render(
    <RewindDialog open onOpenChange={onOpenChange} chatId="c1" messageId={messageId} messageIndex={messageIndex} />,
  );
  return { onOpenChange };
};

const composer = () => {
  const { inputMessage, pendingExplicitSkillActivation } = useChatStore.getState();
  return { inputMessage, pendingExplicitSkillActivation };
};

/** Rewind to `u2` with the server handing back `composerText`, and wait until the transcript has been cut. */
const rewindWithComposerText = async (composerText: string) => {
  useChatStore.setState({
    messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
    loading: false,
  });
  rewindToMessageMock.mockResolvedValue({
    data: {
      success: true,
      deleted_count: 2,
      composer_text: composerText,
      message_index: 1,
      goal_paused: false,
      reverted_files: [],
    },
  });
  renderDialog();
  fireEvent.click(screen.getByText('scopeConversation'));
  fireEvent.click(screen.getByText('confirm'));
  await waitFor(() => {
    expect(useChatStore.getState().messages).toHaveLength(2);
  });
};

describe('RewindDialog', () => {
  beforeEach(() => {
    rewindToMessageMock.mockReset();
    toastMock.mockReset();
    fetchPlanMock.mockClear();
    usePlanStore.setState({ fetchPlan: fetchPlanMock });
    useChatStore.setState({ chatId: 'c1', inputMessage: '', pendingExplicitSkillActivation: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows both scope options and defaults to conversation+files', () => {
    useChatStore.setState({ messages: [], loading: false });
    renderDialog();
    expect(screen.getByText('scopeTitle')).toBeInTheDocument();
    expect(screen.getByText('scopeConversation')).toBeInTheDocument();
    expect(screen.getByText('scopeBoth')).toBeInTheDocument();
    expect(screen.getByText('scopeBothDesc')).toBeInTheDocument();
  });

  it('previews revertible file changes for assistant messages', async () => {
    useChatStore.setState({
      messages: [makeMessage('u1', 'user'), makeMessage('a1', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          path: '/work/a.txt',
          operation: 'write',
          has_original: true,
          timestamp: 1,
          revertible: true,
        },
      ],
    });
    vi.stubGlobal('fetch', fetchMock);
    renderDialog(0, 'u1');
    await waitFor(() => {
      expect(screen.getByText('fileRevertSummary:1')).toBeInTheDocument();
      expect(screen.getByTestId('rewind-files-list')).toBeInTheDocument();
      expect(screen.getByText('a.txt')).toBeInTheDocument();
      expect(screen.getByText('operationModified')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/files/revert/changes/c1/a1',
      expect.objectContaining({ headers: expect.anything() }),
    );
  });

  it('shows empty hint when no snapshots exist', async () => {
    useChatStore.setState({
      messages: [makeMessage('u1', 'user'), makeMessage('a1', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    renderDialog(0, 'u1');
    await waitFor(() => {
      expect(screen.getByText('noFileSnapshots')).toBeInTheDocument();
    });
  });

  it('rewinds conversation-only scope and truncates messages', async () => {
    useChatStore.setState({
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    rewindToMessageMock.mockResolvedValue({
      data: {
        success: true,
        deleted_count: 2,
        composer_text: 'hello world',
        message_index: 1,
        goal_paused: false,
        reverted_files: [],
      },
    });
    renderDialog();
    fireEvent.click(screen.getByText('scopeConversation'));
    fireEvent.click(screen.getByText('confirm'));
    await waitFor(() => {
      expect(rewindToMessageMock).toHaveBeenCalledWith('c1', 'u2', 'conversation');
    });
    expect(useChatStore.getState().messages).toHaveLength(2);
    expect(useChatStore.getState().inputMessage).toBe('hello world');
    expect(fetchPlanMock).toHaveBeenCalledWith('c1');
  });

  it('puts the skill chip and the text of a skill-driven message back into the composer', async () => {
    await rewindWithComposerText('[use writer_skill] draft the memo');

    expect(composer()).toEqual({
      inputMessage: 'draft the memo',
      pendingExplicitSkillActivation: { skillNames: ['writer_skill'], instruction: null },
    });
  });

  it('keeps the instruction of a skill bundle on the chip instead of in the composer text', async () => {
    await rewindWithComposerText('[use a_skill,b_skill] [instruction: be concise] 生成本周报告');

    expect(composer()).toEqual({
      inputMessage: '生成本周报告',
      pendingExplicitSkillActivation: { skillNames: ['a_skill', 'b_skill'], instruction: 'be concise' },
    });
  });

  it('clears a skill chip armed before the rewind when the restored message carries none', async () => {
    useChatStore.setState({ pendingExplicitSkillActivation: { skillNames: ['stale_skill'] } });

    await rewindWithComposerText('hello');

    expect(composer()).toEqual({ inputMessage: 'hello', pendingExplicitSkillActivation: null });
  });

  it.each([
    ['keeps an unsent draft below the restored text', 'hello', 'but shorter', 'hello\n\nbut shorter'],
    ['keeps the draft alone when the restored message has no text', '', 'but shorter', 'but shorter'],
    ['adds nothing for a blank draft', 'hello', ' \n ', 'hello'],
    ['does not repeat a draft that already is the restored text', 'hello', ' hello ', 'hello'],
  ])('%s', async (_name, restored, draft, expected) => {
    useChatStore.setState({ inputMessage: draft });

    await rewindWithComposerText(restored);

    expect(composer().inputMessage).toBe(expected);
  });

  it('keeps a skill chip armed for the kept draft', async () => {
    useChatStore.setState({
      inputMessage: 'but shorter',
      pendingExplicitSkillActivation: { skillNames: ['armed_skill'] },
    });

    await rewindWithComposerText('hello');

    expect(composer()).toEqual({
      inputMessage: 'hello\n\nbut shorter',
      pendingExplicitSkillActivation: { skillNames: ['armed_skill'] },
    });
  });

  it('lets the chip of the restored message replace the one armed for the kept draft', async () => {
    useChatStore.setState({
      inputMessage: 'but shorter',
      pendingExplicitSkillActivation: { skillNames: ['armed_skill'] },
    });

    await rewindWithComposerText('[use writer_skill] hello');

    expect(composer()).toEqual({
      inputMessage: 'hello\n\nbut shorter',
      pendingExplicitSkillActivation: { skillNames: ['writer_skill'], instruction: null },
    });
  });

  it('leaves the open chat alone when the request settles after the user moved to another chat', async () => {
    useChatStore.setState({
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    let settleRewind: ((value: unknown) => void) | undefined;
    rewindToMessageMock.mockReturnValue(
      new Promise((resolve) => {
        settleRewind = resolve;
      }),
    );
    const { onOpenChange } = renderDialog();
    fireEvent.click(screen.getByText('confirm'));

    const otherChatMessages = [{ ...makeMessage('x1', 'user'), chatId: 'c2' }];
    useChatStore.setState({ chatId: 'c2', messages: otherChatMessages, inputMessage: 'typing in c2' });
    settleRewind?.({ data: { success: true, deleted_count: 2, composer_text: 'hello', message_index: 1 } });

    await waitFor(() => {
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
    expect(useChatStore.getState().messages).toBe(otherChatMessages);
    expect(composer()).toEqual({ inputMessage: 'typing in c2', pendingExplicitSkillActivation: null });
    expect(fetchPlanMock).not.toHaveBeenCalled();
    expect(toastMock).toHaveBeenCalledWith({ title: 'success', description: undefined });
  });

  it('marks the chosen scope as pressed', () => {
    useChatStore.setState({ messages: [], loading: false });
    renderDialog();
    const pressed = (label: string) => screen.getByText(label).closest('button')?.getAttribute('aria-pressed');

    expect([pressed('scopeBoth'), pressed('scopeConversation')]).toEqual(['true', 'false']);

    fireEvent.click(screen.getByText('scopeConversation'));

    expect([pressed('scopeBoth'), pressed('scopeConversation')]).toEqual(['false', 'true']);
  });

  it('shows the empty hint without asking for file changes when no assistant message follows the target', async () => {
    useChatStore.setState({
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    renderDialog();

    await waitFor(() => {
      expect(screen.getByText('noFileSnapshots')).toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows files-reverted toast when both scope reverts files', async () => {
    useChatStore.setState({
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    rewindToMessageMock.mockResolvedValue({
      data: {
        success: true,
        deleted_count: 2,
        composer_text: 'hello',
        message_index: 1,
        goal_paused: false,
        reverted_files: ['/work/a.txt'],
      },
    });
    renderDialog();
    fireEvent.click(screen.getByText('confirm'));
    await waitFor(() => {
      expect(rewindToMessageMock).toHaveBeenCalledWith('c1', 'u2', 'both');
    });
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ description: 'filesRevertedToast:1' }));
  });

  it('blocks rewind while the agent is streaming', () => {
    useChatStore.setState({ messages: [], loading: true });
    renderDialog();
    fireEvent.click(screen.getByText('confirm'));
    expect(rewindToMessageMock).not.toHaveBeenCalled();
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ description: 'streamingBlocked' }));
  });

  it('fires one rewind when confirm is clicked twice before the request resolves', async () => {
    useChatStore.setState({
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
    });
    let resolveRewind: ((value: unknown) => void) | undefined;
    rewindToMessageMock.mockReturnValue(
      new Promise((resolve) => {
        resolveRewind = resolve;
      }),
    );
    renderDialog();
    const confirm = screen.getByText('confirm');

    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(rewindToMessageMock).toHaveBeenCalledTimes(1);
    resolveRewind?.({ data: { success: true, deleted_count: 1, composer_text: '', message_index: 0 } });
    await waitFor(() => {
      expect(rewindToMessageMock).toHaveBeenCalledTimes(1);
    });
  });
});
