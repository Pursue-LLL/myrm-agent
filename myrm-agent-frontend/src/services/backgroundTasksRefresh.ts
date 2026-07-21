/** Notify BackgroundTasksPanel to refresh immediately (SSE / chat finish). */
export const BACKGROUND_TASKS_CHANGED_EVENT = 'myrm:background-tasks-changed';

export function notifyBackgroundTasksChanged(): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(BACKGROUND_TASKS_CHANGED_EVENT));
}

export function subscribeBackgroundTasksChanged(listener: () => void): () => void {
  if (typeof window === 'undefined') {
    return () => undefined;
  }
  window.addEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);
  return () => window.removeEventListener(BACKGROUND_TASKS_CHANGED_EVENT, listener);
}

/** Refresh panel/tray when a shell background job finishes (global SSE path). */
export function notifyBackgroundTasksChangedForShellJobFinish(
  meta: Record<string, unknown>,
): void {
  if (meta.kind !== 'background_job_finish') {
    return;
  }
  const chatId = meta.chat_id;
  if (typeof chatId !== 'string' || !chatId.trim()) {
    return;
  }
  notifyBackgroundTasksChanged();
}
