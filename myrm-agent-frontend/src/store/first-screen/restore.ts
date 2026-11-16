/**
 * [INPUT]
 * - ./gate::isFirstScreenSnapshotEnabled (POS: where the snapshot is used at all)
 * - ./envelope::readSnapshotSection (POS: versioned, expiring storage)
 * - ./chatHistorySection / ./projectsSection (POS: section codecs)
 * - @/store/useChatStore, @/store/useProjectStore (POS: the lists the sidebar draws)
 * - @/lib/platform-readiness::getPlatformReadinessSnapshot (POS: whether the backend already answers)
 *
 * [OUTPUT]
 * - seedChatHistoryFromSnapshot: puts the stored chat list into the chat store; true when it did.
 * - seedProjectsFromSnapshot: puts the stored project list into the project store.
 * - resetSeedingForTests
 *
 * [POS]
 * Restore half of the first-screen snapshot: the sidebar shows what it showed last time while the backend is still starting.
 * Each section is offered once per page load, to the first mount that asks. The seeded lists are not confirmed data: the
 * caller keeps loading, and the server's answer replaces them. Pagination stays unset so nothing pages from a list the
 * server has not confirmed.
 */
import { getPlatformReadinessSnapshot } from '@/lib/platform-readiness';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import { chatHistoryFilterKey, decodeChatHistory } from './chatHistorySection';
import { type SnapshotSectionName, readSnapshotSection } from './envelope';
import { isFirstScreenSnapshotEnabled } from './gate';
import { decodeProjects } from './projectsSection';

const offered = new Set<SnapshotSectionName>();

/** The stored section the first time it is asked for in this page load; null afterwards and whenever it cannot help. */
function takeOnce(name: SnapshotSectionName): unknown {
  if (offered.has(name)) {
    return null;
  }
  offered.add(name);
  // A backend that already answers returns the real list as fast as a stored one would be drawn.
  if (!isFirstScreenSnapshotEnabled() || getPlatformReadinessSnapshot().database) {
    return null;
  }
  return readSnapshotSection(name);
}

export function seedChatHistoryFromSnapshot(projectFilter: string | null | undefined): boolean {
  const snapshot = decodeChatHistory(takeOnce('chatHistory'));
  if (snapshot === null || snapshot.items.length === 0 || snapshot.filterKey !== chatHistoryFilterKey(projectFilter)) {
    return false;
  }
  useChatStore.setState({
    chatHistoryItems: snapshot.items,
    chatHistoryPagination: null,
    chatHistoryLoading: false,
    chatHistoryError: null,
  });
  return true;
}

export function seedProjectsFromSnapshot(): void {
  const projects = decodeProjects(takeOnce('projects'));
  const { loaded, projects: current } = useProjectStore.getState();
  if (projects === null || projects.length === 0 || loaded || current.length > 0) {
    return;
  }
  // `loaded` stays false: the project bar still fetches, and the fetched list replaces this one.
  useProjectStore.setState({ projects });
}

/** @internal test helper */
export function resetSeedingForTests(): void {
  offered.clear();
}
