import { describe, expect, it, vi } from 'vitest';
import { MANAGED_POLICY_UPDATED_EVENT } from '@/lib/managedPolicyEffectiveEvents';
import {
  emit,
  installGlobalEventsLifecycle,
  mocks,
  mountGlobalEvents,
  recordWindowEvents,
  toastOptions,
} from './globalEventsTestKit';

const COMMON_DEPS = { t: expect.any(Function), notifyIfLeader: expect.any(Function) };

describe('useGlobalEvents: events relayed to the window', () => {
  installGlobalEventsLifecycle();

  it.each([
    ['memory_history_updated', 'memory_history_updated'],
    ['subagents_updated', 'subagents_updated'],
    ['cron_updated', 'cron_updated'],
    ['budget_updated', 'budget_updated'],
    ['skill_pool_updated', 'skill_pool_updated'],
    ['goal:branch_switched', 'goal:branch_switched'],
    ['workspace_file_changed', 'workspace-file-changed'],
    ['async_agent_stream_chunk', 'async-agent-stream-chunk'],
    ['extension_status_changed', 'extension-status-changed'],
    ['managed_policy_updated', MANAGED_POLICY_UPDATED_EVENT],
  ])('%s is relayed as the %s window event carrying the payload data', (type, windowEvent) => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit(type, { id: 'x-1' });

    expect(events()).toEqual([{ type: windowEvent, detail: { id: 'x-1' } }]);
    expect(mocks.toast.info).not.toHaveBeenCalled();
    expect(mocks.notify).not.toHaveBeenCalled();
  });

  it('ignores an unknown event type and a malformed frame', () => {
    const { source } = mountGlobalEvents();
    const events = recordWindowEvents();

    emit('totally_unknown', { a: 1 });
    expect(() => source.onmessage?.({ data: 'not json' } as MessageEvent<string>)).not.toThrow();

    expect(events()).toEqual([]);
    expect(mocks.toast.info).not.toHaveBeenCalled();
  });

  it.each(['channel_connected', 'channel_disconnected'])('%s relays the channel status change', (type) => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit(type, { channel: 'slack', status: 'ok' });

    expect(events()).toEqual([{ type: 'channel-status-change', detail: { channel: 'slack', status: 'ok', type } }]);
  });

  it('groups_updated relays the channel with a numeric count, defaulting to zero', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('groups_updated', { channel: 'slack', count: 3 });
    emit('groups_updated', { channel: 'slack' });

    expect(events()).toEqual([
      { type: 'groups-updated', detail: { channel: 'slack', count: 3 } },
      { type: 'groups-updated', detail: { channel: 'slack', count: 0 } },
    ]);
  });

  it('pairing_pending raises an actionable toast that opens the channel settings', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('pairing_pending', { channel: 'telegram', sender_id: '42', display_name: 'Ann' });

    const options = toastOptions(mocks.toast.info);
    expect(mocks.toast.info.mock.calls[0][0]).toBe('pairingPending');
    expect(options).toMatchObject({ id: 'pairing-pending-telegram-42', duration: 30_000, dismissible: true });
    options.action?.onClick();
    expect(mocks.toast.dismiss).toHaveBeenCalledWith('pairing-pending-telegram-42');
    expect(mocks.router.push).toHaveBeenCalledWith('/settings/channels');
    expect(events()).toEqual([{ type: 'pairings-updated', detail: null }]);
  });

  it('message_dead_lettered hands the payload to the dead-letter toast', () => {
    mountGlobalEvents();

    emit('message_dead_lettered', { channel: 'slack' });

    expect(mocks.showMessageDeadLetteredToast).toHaveBeenCalledWith({ channel: 'slack' }, COMMON_DEPS);
  });

  it('approval_required toasts, notifies the leader tab and relays the normalized request', async () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('approval_required', { action_type: 'shell', approval_id: 'ap-1' });

    expect(mocks.toast.info.mock.calls[0][0]).toBe('approvalRequired');
    expect(toastOptions(mocks.toast.info)).toMatchObject({ duration: 8_000, dismissible: true });
    expect(mocks.notify).toHaveBeenCalledWith('approvalRequired', {
      body: 'shell',
      fallbackToToast: false,
      onClick: expect.any(Function),
    });
    expect(events()).toEqual([
      { type: 'approval-required', detail: { action_type: 'shell', approval_id: 'ap-1', normalized: true } },
    ]);

    toastOptions(mocks.toast.info).action?.onClick();
    await vi.dynamicImportSettled();
    expect(mocks.openApproval).toHaveBeenCalledWith({ action_type: 'shell', approval_id: 'ap-1', normalized: true });
  });

  it('approval_resolved closes the approval only when it carries an id', async () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('approval_resolved', { approval_id: 'ap-1' });
    emit('approval_resolved', {});
    await vi.dynamicImportSettled();

    expect(mocks.closeApproval).toHaveBeenCalledTimes(1);
    expect(mocks.closeApproval).toHaveBeenCalledWith('ap-1');
    expect(events().map((event) => event.type)).toEqual(['approval_resolved', 'approval_resolved']);
  });

  it('memory_operation, locator_healed, mcp and oauth events delegate to their toasts', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('memory_operation', { op: 'saved' });
    emit('locator_healed', { selector: '#a' });
    emit('mcp_auth_required', { server: 'gh' });
    emit('oauth_reauth_required', { provider: 'google' });

    expect(mocks.showMemoryOperationToasts).toHaveBeenCalledWith(
      { op: 'saved' },
      { t: expect.any(Function), router: mocks.router },
    );
    expect(mocks.showLocatorHealedToast).toHaveBeenCalledWith({ selector: '#a' }, { t: expect.any(Function) });
    const reauthDeps = { ...COMMON_DEPS, router: mocks.router, toast: expect.any(Object) };
    expect(mocks.showMcpAuthRequiredToast).toHaveBeenCalledWith({ server: 'gh' }, reauthDeps);
    expect(mocks.showOAuthReauthRequiredToast).toHaveBeenCalledWith({ provider: 'google' }, reauthDeps);
    expect(events()).toEqual([
      { type: 'memory_operation', detail: { op: 'saved' } },
      { type: 'locator_healed', detail: { selector: '#a' } },
    ]);
  });

  it('kanban_task_updated delegates to the kanban toast and relays the update', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('kanban_task_updated', { action: 'moved' });

    expect(mocks.showKanbanTaskToast).toHaveBeenCalledWith(
      { action: 'moved' },
      { ...COMMON_DEPS, tKanban: expect.any(Function), router: mocks.router, pushToast: expect.any(Object) },
    );
    expect(events()).toEqual([{ type: 'kanban-task-updated', detail: { action: 'moved' } }]);
  });

  it('idle_status relays the status and offers the subsumption undo', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('idle_status', { phase: 'dreaming' });

    expect(events()).toEqual([{ type: 'idle-status', detail: { phase: 'dreaming' } }]);
    expect(mocks.showSubsumptionUndoToast).toHaveBeenCalledWith(
      { phase: 'dreaming' },
      { t: expect.any(Function), tIdle: expect.any(Function), pushToast: expect.any(Object) },
    );
  });

  it('run_digest_updated relays the digest, dropping an empty one', () => {
    mountGlobalEvents();
    const events = recordWindowEvents();

    emit('run_digest_updated', { chat_id: 'c1', digest: { steps: 2 } });
    emit('run_digest_updated', { chat_id: 'c1', digest: {} });
    emit('run_digest_updated', { chat_id: 7 });

    expect(events()).toEqual([
      { type: 'run-digest-updated', detail: { chat_id: 'c1', digest: { steps: 2 } } },
      { type: 'run-digest-updated', detail: { chat_id: 'c1', digest: undefined } },
      { type: 'run-digest-updated', detail: { chat_id: '', digest: undefined } },
    ]);
  });
});
