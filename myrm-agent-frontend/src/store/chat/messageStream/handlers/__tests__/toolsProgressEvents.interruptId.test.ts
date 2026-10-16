/**
 * The approval cards a paused run announces carry the interrupt they answer, and an interrupt announced again
 * (the run paused on it once more after a sibling card was answered) never queues a second card.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useToolApprovalStore from '@/store/useToolApprovalStore';
import { toolsProgressEvents } from '../toolsProgressEvents';
import type { StreamCtx } from '../../streamContext';

function approvalPayload(action: string) {
  return {
    actionRequests: [{ action, args: { command: action }, description: `run ${action}` }],
    reviewConfigs: [{}],
    extensions: { approval: { requestId: `req-${action}` } },
  };
}

function makeCtx(type: string, data: unknown, interruptId?: string): StreamCtx {
  return {
    data: { type, messageId: 'msg-1', data, ...(interruptId ? { interruptId } : {}) } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: { setLoading: vi.fn(), setMessages: vi.fn() } as never,
    files: [],
  };
}

function queuedCards(): Array<[string, string | undefined]> {
  return useToolApprovalStore.getState().queue.map((request) => [request.toolName, request.interruptId]);
}

describe('toolsProgressEvents approval cards and interrupt ids', () => {
  beforeEach(() => {
    useToolApprovalStore.getState().clearAll();
  });

  it('queues a card per interrupt, each keeping the id of the interrupt it answers', async () => {
    await toolsProgressEvents(makeCtx('tool_approval_request', approvalPayload('alpha'), 'int-a'));
    await toolsProgressEvents(makeCtx('tool_approval_request', approvalPayload('beta'), 'int-b'));

    expect(queuedCards()).toEqual([
      ['alpha', 'int-a'],
      ['beta', 'int-b'],
    ]);
  });

  it('keeps the id when the harness announces the interrupt as approval_required', async () => {
    await toolsProgressEvents(makeCtx('approval_required', approvalPayload('alpha'), 'int-a'));

    expect(queuedCards()).toEqual([['alpha', 'int-a']]);
  });

  it('does not queue a second card when the same interrupt is announced again', async () => {
    await toolsProgressEvents(makeCtx('tool_approval_request', approvalPayload('alpha'), 'int-a'));
    await toolsProgressEvents(makeCtx('tool_approval_request', approvalPayload('alpha'), 'int-a'));

    expect(queuedCards()).toEqual([['alpha', 'int-a']]);
  });
});
