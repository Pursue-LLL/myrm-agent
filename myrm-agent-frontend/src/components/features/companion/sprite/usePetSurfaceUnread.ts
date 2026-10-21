/**
 * [INPUT]
 * - petSurfaceAwayCompletion (POS: away-completion CustomEvent for mail unread)
 *
 * [OUTPUT]
 * - usePetSurfaceUnread: { unread, clearUnread }
 *
 * [POS]
 * Mail badge state for popped-out pet surface when agent completes while user is away.
 */

import { useCallback, useEffect, useState } from 'react';

import { PET_SURFACE_AWAY_COMPLETION_EVENT } from './petSurfaceAwayCompletion';

export function usePetSurfaceUnread(enabled: boolean): {
  unread: boolean;
  clearUnread: () => void;
} {
  const [unread, setUnread] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const onAwayCompletion = () => {
      setUnread(true);
    };

    window.addEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, onAwayCompletion);
    return () => {
      window.removeEventListener(PET_SURFACE_AWAY_COMPLETION_EVENT, onAwayCompletion);
    };
  }, [enabled]);

  const clearUnread = useCallback(() => {
    setUnread(false);
  }, []);

  return { unread, clearUnread };
}
