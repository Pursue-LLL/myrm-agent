import { useCallback, useState } from 'react';
import { getCuratorHistory, type CuratorHistoryEntry } from '@/services/skill';

/** Lazy-loads the recent sweep history the first time the section opens; `reloadIfOpen` refreshes it after a new run. */
export function useCuratorHistory() {
  const [entries, setEntries] = useState<CuratorHistoryEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await getCuratorHistory(10));
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const toggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    if (next && entries.length === 0) {
      load();
    }
  }, [open, entries.length, load]);

  const reloadIfOpen = useCallback(() => {
    if (open) {
      load();
    }
  }, [open, load]);

  return { sectionProps: { open, loading, entries, onToggle: toggle }, reloadIfOpen };
}
