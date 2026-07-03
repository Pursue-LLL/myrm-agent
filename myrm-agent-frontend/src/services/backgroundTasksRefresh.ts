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
