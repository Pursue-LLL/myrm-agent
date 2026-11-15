/**
 * [INPUT]
 * - ./gate::isFirstScreenSnapshotEnabled (POS: where the snapshot is used at all)
 * - ./envelope::writeSnapshotSection / flushSnapshot (POS: windowed storage)
 * - ./chatHistorySection / ./projectsSection (POS: section codecs)
 * - @/store/useChatStore, @/store/useProjectStore (POS: the lists the sidebar draws)
 *
 * [OUTPUT]
 * - startFirstScreenSnapshotWriter: starts storing the first-screen lists as they change; returns the stop function.
 *
 * [POS]
 * Store half of the first-screen snapshot. A list is stored only while it is data the backend confirmed in this session: the
 * chat list carries the pagination of the server's answer (a restored list does not), is idle, and is not narrowed by source or
 * keyword; the project list is stored once fetched. What is stored therefore never comes from a previous snapshot. Taking the
 * snapshot runs inside the store update that triggered it, so a failure here is logged and never allowed to reach that update.
 */
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import { chatHistoryFilterKey, encodeChatHistory } from './chatHistorySection';
import { flushSnapshot, writeSnapshotSection } from './envelope';
import { isFirstScreenSnapshotEnabled } from './gate';
import { encodeProjects } from './projectsSection';

/** The snapshot is a start-up courtesy: a failure while taking it must not break the store update it rides on. */
function guarded(store: () => void): void {
  try {
    store();
  } catch (error) {
    console.warn('First-screen snapshot skipped:', error);
  }
}

function storeChatHistory(): void {
  const state = useChatStore.getState();
  const confirmed =
    state.chatHistoryPagination !== null && !state.chatHistoryLoading && state.chatHistoryError === null;
  const unfiltered = state.chatHistorySourceFilter === null && state.chatHistorySearchKeyword.trim() === '';
  if (!confirmed || !unfiltered) {
    return;
  }
  const filterKey = chatHistoryFilterKey(useProjectStore.getState().activeFilter);
  writeSnapshotSection('chatHistory', encodeChatHistory(filterKey, state.chatHistoryItems));
}

function storeProjects(): void {
  const { projects, loaded } = useProjectStore.getState();
  if (loaded) {
    writeSnapshotSection('projects', encodeProjects(projects));
  }
}

export function startFirstScreenSnapshotWriter(): () => void {
  if (!isFirstScreenSnapshotEnabled()) {
    return () => undefined;
  }

  const stopChat = useChatStore.subscribe((state, previous) => {
    // The chat store changes many times a second while a reply streams: only the list's own fields matter here.
    if (
      state.chatHistoryItems !== previous.chatHistoryItems ||
      state.chatHistoryPagination !== previous.chatHistoryPagination ||
      state.chatHistoryLoading !== previous.chatHistoryLoading ||
      state.chatHistoryError !== previous.chatHistoryError
    ) {
      guarded(storeChatHistory);
    }
  });
  const stopProjects = useProjectStore.subscribe((state, previous) => {
    if (state.projects !== previous.projects || state.loaded !== previous.loaded) {
      guarded(storeProjects);
    }
  });

  const flushWhenHidden = (): void => {
    if (document.visibilityState === 'hidden') {
      flushSnapshot();
    }
  };
  window.addEventListener('pagehide', flushSnapshot);
  document.addEventListener('visibilitychange', flushWhenHidden);

  // The stores may already hold confirmed lists when the writer starts.
  guarded(storeChatHistory);
  guarded(storeProjects);

  return () => {
    stopChat();
    stopProjects();
    window.removeEventListener('pagehide', flushSnapshot);
    document.removeEventListener('visibilitychange', flushWhenHidden);
    flushSnapshot();
  };
}
