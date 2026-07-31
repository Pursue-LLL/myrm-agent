/**
 * [INPUT]
 * - (browser EventSource) `/api/v1/tasks/stream` (POS: server task lifecycle SSE hub)
 *
 * [OUTPUT]
 * - subscribeTaskUpdateEvents: multiplexed task_update listener with ref-counted SSE connection
 * - isTaskUpdateEventStreamOpen: connection health probe for poll fallback
 * - TaskUpdateEvent: normalized SSE payload shape
 *
 * [POS]
 * Frontend task SSE fan-out layer. Chat task cards, BackgroundTasksPanel, tray, and global notify share one EventSource.
 */

export interface TaskUpdateEvent {
  task_id: string;
  status?: string;
  task_type?: string;
  sync_required?: boolean;
  timestamp?: number;
}

type TaskUpdateListener = (event: TaskUpdateEvent) => void;

let eventSource: EventSource | null = null;
let subscriberCount = 0;
const listeners = new Set<TaskUpdateListener>();

function dispatchEvent(event: TaskUpdateEvent): void {
  for (const listener of listeners) {
    listener(event);
  }
}

function ensureEventSource(): void {
  if (eventSource) {
    return;
  }

  eventSource = new EventSource('/api/v1/tasks/stream');
  eventSource.addEventListener('task_update', (rawEvent) => {
    try {
      const parsed = JSON.parse(rawEvent.data) as unknown;
      if (!parsed || typeof parsed !== 'object') {
        dispatchEvent({ task_id: '', sync_required: true });
        return;
      }
      dispatchEvent(parsed as TaskUpdateEvent);
    } catch {
      dispatchEvent({ task_id: '', sync_required: true });
    }
  });
}

function closeEventSourceIfIdle(): void {
  if (subscriberCount <= 0 && eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

export function subscribeTaskUpdateEvents(listener: TaskUpdateListener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  ensureEventSource();

  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    closeEventSourceIfIdle();
  };
}

/** True when the shared task SSE hub is connected; used by hooks for poll fallback. */
export function isTaskUpdateEventStreamOpen(): boolean {
  return eventSource !== null && eventSource.readyState === EventSource.OPEN;
}

/** Test-only reset for vitest isolation. */
export function resetTaskUpdateEventStreamForTests(): void {
  listeners.clear();
  subscriberCount = 0;
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}
