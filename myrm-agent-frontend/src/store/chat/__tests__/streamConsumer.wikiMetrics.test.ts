/**
 * The wiki-metric bookkeeping of the stream consumer: a query counts as answered once, on the first valid business
 * frame, and a stream that delivers none counts nothing.
 */
import { describe, expect, it } from 'vitest';
import {
  approvalState,
  createActions,
  createBaseState,
  createSseResponse,
  installStreamConsumerLifecycle,
  mockConsumePendingChatWikiQuerySuccess,
  mockCreateMessageRequest,
  mockHandleMessageStream,
  mockParseSseEnvelope,
  mockRecordWikiQuerySubmitted,
  mockResolveChatWikiEvidenceContext,
} from './streamConsumerTestKit';
import { executeStreamWithRetry } from '../streamConsumer';
import type { Message } from '@/store/chat/types';

describe('streamConsumer wiki query metrics', () => {
  installStreamConsumerLifecycle();

  it('records wiki query success exactly once on first valid business frame', async () => {
    const state = createBaseState({
      chatId: 'chat-success',
      messages: [{ role: 'assistant', messageId: 'a-1', content: '', createdAt: new Date() } as Message],
    });
    const actions = createActions(state);
    const abortController = new AbortController();
    approvalState.queue = [{}];
    mockCreateMessageRequest.mockResolvedValueOnce(
      createSseResponse('data: {"type":"message","messageId":"msg-success","data":"ok"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'msg-success', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-success',
        state,
        actions,
        null,
        abortController,
        false,
        '',
        undefined,
        undefined,
        true,
      ),
    ).resolves.toBeUndefined();

    expect(mockResolveChatWikiEvidenceContext).toHaveBeenCalledTimes(1);
    expect(mockResolveChatWikiEvidenceContext).toHaveBeenCalledWith(state.messages, 'chat-success');
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledWith('chat', 'chat:a-1', 0);
  });

  it('does not record wiki query success when no valid business frame arrives', async () => {
    const state = createBaseState({
      chatId: 'chat-no-frame',
      messages: [{ role: 'assistant', messageId: 'a-1', content: '', createdAt: new Date() } as Message],
    });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValueOnce(createSseResponse('data: not-json\n\n'));

    await expect(
      executeStreamWithRetry(
        'hello',
        'msg-no-frame',
        state,
        actions,
        null,
        abortController,
        false,
        '',
        undefined,
        undefined,
        true,
      ),
    ).resolves.toBeUndefined();

    expect(mockResolveChatWikiEvidenceContext).not.toHaveBeenCalled();
    expect(mockRecordWikiQuerySubmitted).not.toHaveBeenCalled();
  });

  it('records queued steer wiki query success on first matching business frame', async () => {
    const state = createBaseState({ chatId: 'chat-steer-success' });
    const actions = createActions(state);
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValueOnce(
      createSseResponse('data: {"type":"message","messageId":"msg-steer","data":"ok"}\n\n'),
    );
    mockParseSseEnvelope.mockReturnValue({ type: 'message', messageId: 'msg-steer', data: 'ok' });
    mockHandleMessageStream.mockResolvedValue({ added: true, recievedMessage: 'ok' });
    mockConsumePendingChatWikiQuerySuccess.mockReturnValueOnce({
      contextKey: 'chat:steer',
      turnDistance: 2,
    });

    await expect(
      executeStreamWithRetry('hello', 'msg-steer', state, actions, null, abortController, false, ''),
    ).resolves.toBeUndefined();

    expect(mockConsumePendingChatWikiQuerySuccess).toHaveBeenCalledWith('chat-steer-success', 'msg-steer');
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledTimes(1);
    expect(mockRecordWikiQuerySubmitted).toHaveBeenCalledWith('chat', 'chat:steer', 2);
    expect(mockResolveChatWikiEvidenceContext).not.toHaveBeenCalled();
  });
});
