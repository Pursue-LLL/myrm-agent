import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  MultiWindowCanvasStateBus,
  type SessionFocusEvent,
  type CanvasStateUpdateEvent,
  type ToolExecutionSyncEvent,
  type ConfigSyncEvent,
} from '../multiWindowCanvasStateBus';

describe('MultiWindowCanvasStateBus', () => {
  beforeEach(() => {
    MultiWindowCanvasStateBus.resetInstance();
  });

  afterEach(() => {
    MultiWindowCanvasStateBus.resetInstance();
    vi.restoreAllMocks();
  });

  it('publishes and receives local events correctly', () => {
    const bus = new MultiWindowCanvasStateBus('test_bus_1');
    const focusHandler = vi.fn();

    const unsub = bus.subscribe<SessionFocusEvent>('SESSION_FOCUS', focusHandler);

    bus.publish({
      type: 'SESSION_FOCUS',
      sessionId: 'sess_123',
      activeTabId: 'tab_a',
    });

    expect(focusHandler).toHaveBeenCalledTimes(1);
    const received = focusHandler.mock.calls[0][0] as SessionFocusEvent;
    expect(received.type).toBe('SESSION_FOCUS');
    expect(received.sessionId).toBe('sess_123');
    expect(received.activeTabId).toBe('tab_a');
    expect(received.senderWindowId).toBe(bus.windowInstanceId);
    expect(typeof received.timestamp).toBe('number');

    // Unsubscribe
    unsub();
    bus.publish({
      type: 'SESSION_FOCUS',
      sessionId: 'sess_456',
    });
    expect(focusHandler).toHaveBeenCalledTimes(1);
    bus.destroy();
  });

  it('dispatches different event types to respective subscribers without cross-talk', () => {
    const bus = new MultiWindowCanvasStateBus('test_bus_2');
    const canvasHandler = vi.fn();
    const toolHandler = vi.fn();
    const configHandler = vi.fn();

    bus.subscribe<CanvasStateUpdateEvent>('CANVAS_STATE_UPDATE', canvasHandler);
    bus.subscribe<ToolExecutionSyncEvent>('TOOL_EXECUTION_SYNC', toolHandler);
    bus.subscribe<ConfigSyncEvent>('CONFIG_SYNC', configHandler);

    bus.publish({
      type: 'CANVAS_STATE_UPDATE',
      canvasId: 'cv_001',
      nodeCount: 12,
      revision: 3,
    });

    bus.publish({
      type: 'TOOL_EXECUTION_SYNC',
      callId: 'call_99',
      toolName: 'bash',
      status: 'completed',
    });

    expect(canvasHandler).toHaveBeenCalledTimes(1);
    expect(toolHandler).toHaveBeenCalledTimes(1);
    expect(configHandler).toHaveBeenCalledTimes(0);

    bus.destroy();
  });

  it('filters loopback messages originating from the same window instance', () => {
    const bus = new MultiWindowCanvasStateBus('test_bus_3');
    const handler = vi.fn();
    bus.subscribe('SESSION_FOCUS', handler);

    // Simulate an echo message from the same windowInstanceId
    const selfEchoMessage: SessionFocusEvent = {
      type: 'SESSION_FOCUS',
      sessionId: 'sess_echo',
      senderWindowId: bus.windowInstanceId,
      timestamp: Date.now(),
    };

    // Invoke handleIncomingMessageForTest to verify loopback rejection
    bus.handleIncomingMessageForTest(selfEchoMessage);

    expect(handler).not.toHaveBeenCalled();

    // Now simulate an incoming message from a peer window
    const peerMessage: SessionFocusEvent = {
      type: 'SESSION_FOCUS',
      sessionId: 'sess_peer',
      senderWindowId: 'win_remote_peer_999',
      timestamp: Date.now(),
    };

    bus.handleIncomingMessageForTest(peerMessage);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].sessionId).toBe('sess_peer');

    bus.destroy();
  });

  it('stops dispatching events after destroy is invoked', () => {
    const bus = new MultiWindowCanvasStateBus('test_bus_4');
    const handler = vi.fn();
    bus.subscribe('CONFIG_SYNC', handler);

    bus.destroy();

    bus.publish({
      type: 'CONFIG_SYNC',
      scope: 'model',
      key: 'temperature',
      value: 0.7,
    });

    expect(handler).not.toHaveBeenCalled();
  });
});
