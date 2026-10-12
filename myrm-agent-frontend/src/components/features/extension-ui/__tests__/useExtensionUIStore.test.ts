import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useExtensionUIStore } from '@/store/useExtensionUIStore';
import * as extensionUIService from '@/services/extensionUIService';
import type { UIRequestItem } from '../extensionUITypes';

vi.mock('@/services/extensionUIService', () => ({
  submitUIResponse: vi.fn().mockResolvedValue({ resolved: true, request_id: 'req-1' }),
  cancelUIRequest: vi.fn().mockResolvedValue({ cancelled: true, request_id: 'req-1' }),
  fetchPendingUIRequests: vi.fn().mockResolvedValue([]),
}));

describe('useExtensionUIStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExtensionUIStore.getState().reset();
  });

  it('enqueues request and activates first immediately', () => {
    const req1: UIRequestItem = {
      request_id: 'req-1',
      request_type: 'select',
      title: 'Select deploy env',
      options: [
        { label: 'Production', value: 'prod' },
        { label: 'Staging', value: 'staging' },
      ],
      default_value: 'staging',
    };

    useExtensionUIStore.getState().enqueueRequest(req1);

    const state = useExtensionUIStore.getState();
    expect(state.activeRequest?.request_id).toBe('req-1');
    expect(state.selectedValue).toBe('staging');
    expect(state.queue).toHaveLength(0);
  });

  it('queues additional requests when one is already active', () => {
    const req1: UIRequestItem = {
      request_id: 'req-1',
      request_type: 'confirm',
      title: 'Confirm A',
    };
    const req2: UIRequestItem = {
      request_id: 'req-2',
      request_type: 'input',
      title: 'Enter B',
      default_value: 'initial-val',
    };

    useExtensionUIStore.getState().enqueueRequest(req1);
    useExtensionUIStore.getState().enqueueRequest(req2);

    expect(useExtensionUIStore.getState().activeRequest?.request_id).toBe('req-1');
    expect(useExtensionUIStore.getState().queue).toHaveLength(1);
    expect(useExtensionUIStore.getState().queue[0].request_id).toBe('req-2');
  });

  it('resolves active request and shifts next from queue', async () => {
    useExtensionUIStore.setState({ chatId: 'chat-123' });

    const req1: UIRequestItem = {
      request_id: 'req-1',
      request_type: 'input',
      title: 'Enter key',
    };
    const req2: UIRequestItem = {
      request_id: 'req-2',
      request_type: 'select',
      title: 'Select option',
      options: [{ label: 'Opt 1', value: 'val-1' }],
    };

    useExtensionUIStore.getState().enqueueRequest(req1);
    useExtensionUIStore.getState().enqueueRequest(req2);
    useExtensionUIStore.getState().setInputValue('my-secret-key');

    const ok = await useExtensionUIStore.getState().resolveCurrent();
    expect(ok).toBe(true);

    expect(extensionUIService.submitUIResponse).toHaveBeenCalledWith('chat-123', 'req-1', {
      value: 'my-secret-key',
      cancelled: false,
    });

    const state = useExtensionUIStore.getState();
    expect(state.activeRequest?.request_id).toBe('req-2');
    expect(state.selectedValue).toBe('val-1');
    expect(state.queue).toHaveLength(0);
  });

  it('cancels active request properly', async () => {
    useExtensionUIStore.setState({ chatId: 'chat-123' });

    const req: UIRequestItem = {
      request_id: 'req-1',
      request_type: 'confirm',
      title: 'Delete everything?',
    };

    useExtensionUIStore.getState().enqueueRequest(req);
    const ok = await useExtensionUIStore.getState().cancelCurrent('User rejected');
    expect(ok).toBe(true);

    expect(extensionUIService.cancelUIRequest).toHaveBeenCalledWith(
      'chat-123',
      'req-1',
      'User rejected',
    );
    expect(useExtensionUIStore.getState().activeRequest).toBeNull();
  });
});
