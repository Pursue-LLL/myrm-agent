/**
 * How a refused or malformed agent-stream request is reported: JSON acks, structured error details, empty and
 * body-less answers, and rejections that are no Error.
 */
import { describe, expect, it } from 'vitest';
import {
  createActions,
  createBaseState,
  installStreamConsumerLifecycle,
  mockCreateMessageRequest,
  mockHandleMessageStream,
} from './streamConsumerTestKit';
import { executeStreamWithRetry } from '../streamConsumer';
import { RequestRefusedError } from '../streamErrors';

installStreamConsumerLifecycle();

describe('agent-stream protocol and error payload parsing', () => {
  it('refuses a JSON 200 ack instead of waiting for chunks that never come', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(
      new Response(JSON.stringify({ status: 'accepted', message_id: 'm-1' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(
      executeStreamWithRetry('hello', 'msg-json-ack', state, actions, null, new AbortController(), false, ''),
    ).rejects.toBeInstanceOf(RequestRefusedError);
    expect(mockHandleMessageStream).not.toHaveBeenCalled();
  });

  it('surfaces structured detail and error_code from a refused request', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'model not configured', error_code: 'MODEL_MISSING' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(
      executeStreamWithRetry('hello', 'msg-refused', state, actions, null, new AbortController(), false, ''),
    ).rejects.toMatchObject({ message: 'model not configured', errorCode: 'MODEL_MISSING' });
  });

  it('falls back to the raw body when a refused response carries a non-object payload', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(new Response('[]', { status: 400 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-refused-array', state, actions, null, new AbortController(), false, ''),
    ).rejects.toBeInstanceOf(RequestRefusedError);
  });
});

describe('agent-stream defensive edges', () => {
  it('refuses an empty error body without inventing a message', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(new Response('', { status: 400 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-empty-error', state, actions, null, new AbortController(), false, ''),
    ).rejects.toBeInstanceOf(RequestRefusedError);
  });

  it('rejects a 200 response that carries no body', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockResolvedValue(new Response(null, { status: 200 }));

    await expect(
      executeStreamWithRetry('hello', 'msg-no-body', state, actions, null, new AbortController(), false, ''),
    ).rejects.toThrow('No response body');
  });

  it('rethrows a non-Error rejection unchanged', async () => {
    const state = createBaseState();
    const actions = createActions(state);
    mockCreateMessageRequest.mockRejectedValue('boom');

    await expect(
      executeStreamWithRetry('hello', 'msg-non-error', state, actions, null, new AbortController(), false, ''),
    ).rejects.toBe('boom');
  });
});
