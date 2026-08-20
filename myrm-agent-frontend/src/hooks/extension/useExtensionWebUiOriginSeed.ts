'use client';

import { useEffect, useRef } from 'react';
import { getExtensionClipAgentConfig, updateExtensionClipAgentConfig } from '@/services/extension';

/**
 * Persist WebUI origin for extension wiki-clip deep links (Duplicate Review, security, raw).
 * Runs once per app mount; merges with existing clip agent_id.
 */
export function useExtensionWebUiOriginSeed(): void {
  const seededRef = useRef(false);

  useEffect(() => {
    if (seededRef.current || typeof window === 'undefined') {
      return;
    }
    seededRef.current = true;

    const origin = window.location.origin;
    void (async () => {
      try {
        const cfg = await getExtensionClipAgentConfig();
        if (cfg.web_ui_origin === origin) {
          return;
        }
        await updateExtensionClipAgentConfig(cfg.agent_id, origin);
      } catch {
        // Non-fatal: extension deep links require a later successful seed.
      }
    })();
  }, []);
}
