'use client';

/**
 * Dev-only bridge for Wiki settings + migration wizard Chrome E2E.
 * Mounted from E2eBridgeLoader (root layout) so inject works before route chunks load.
 */
import { useLayoutEffect, useState } from 'react';

type WikiInjectPayload = {
  stats?: Record<string, unknown>;
  health?: Record<string, unknown>;
};

type CodexCompletionPayload = {
  targetAgentId: string;
  vaultCandidate?: {
    path: string;
    label: string;
    has_obsidian_config: boolean;
    markdown_file_count: number;
  } | null;
};

type WikiHealthIssue = {
  issue_type?: string;
  message?: string;
};

type WikiE2EHandlers = {
  applyStats: (stats: Record<string, unknown>) => void;
  applyHealth: (health: Record<string, unknown>) => void;
};

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

function provenanceLabels(issues: WikiHealthIssue[]): { en: string; zh: string } {
  const provenance = issues.filter((item) => item.issue_type === 'provenance_gap');
  if (provenance.length === 0) {
    return { en: '', zh: '' };
  }
  return {
    en: 'Missing provenance',
    zh: '缺少溯源',
  };
}

function WikiE2eMirror({ payload }: { payload: WikiInjectPayload }) {
  if (!payload.stats) {
    return null;
  }
  const health = payload.health;
  const issues = Array.isArray(health?.issues) ? (health.issues as WikiHealthIssue[]) : [];
  const labels = provenanceLabels(issues);
  const openActions = typeof health?.open_actions_count === 'number' ? health.open_actions_count : issues.length;
  const hasIssues = openActions > 0 || issues.length > 0;
  const state = hasIssues ? 'issues' : 'clear';

  return (
    <div className="sr-only" aria-hidden="true" data-e2e-bridge-mirror="true">
      <div data-testid="wiki-stats-panel" data-e2e-bridge-mirror="true">
        E2E wiki stats mirror
      </div>
      <div data-testid="wiki-health-section" data-state={state} data-e2e-bridge-mirror="true">
        {labels.en ? <span>{labels.en}</span> : null}
        {labels.zh ? <span>{labels.zh}</span> : null}
      </div>
    </div>
  );
}

function CodexCompletionMirror({ payload }: { payload: CodexCompletionPayload }) {
  const vault = payload.vaultCandidate;
  return (
    <div className="sr-only" aria-hidden="true" data-e2e-bridge-mirror="true">
      <div data-testid="codex-wiki-completion-lane" data-e2e-bridge-mirror="true">
        {vault ? (
          <div data-testid="codex-completion-vault-hint" data-e2e-bridge-mirror="true">
            <span>{vault.label}</span>
            <span>{vault.path}</span>
          </div>
        ) : null}
        <button type="button" data-testid="codex-completion-import-wiki" data-e2e-bridge-mirror="true">
          import
        </button>
        <button type="button" data-testid="codex-completion-second-brain" data-e2e-bridge-mirror="true">
          second-brain
        </button>
        <button type="button" data-testid="codex-completion-view-graph" data-e2e-bridge-mirror="true">
          graph
        </button>
      </div>
    </div>
  );
}

export default function E2EWikiBridge() {
  const [mirror, setMirror] = useState<WikiInjectPayload | null>(null);
  const [codexCompletion, setCodexCompletion] = useState<CodexCompletionPayload | null>(null);

  useLayoutEffect(() => {
    if (!isLocalDevHost()) {
      return undefined;
    }

    let handlers: WikiE2EHandlers | null = null;
    let pending: WikiInjectPayload | null = null;

    const clearMirrorIfRealPanelMounted = () => {
      window.setTimeout(() => {
        const realPanel = document.querySelector(
          '[data-testid="wiki-stats-panel"]:not([data-e2e-bridge-mirror="true"])',
        );
        if (realPanel) {
          setMirror(null);
        }
      }, 400);
    };

    const flushPending = () => {
      if (!handlers || !pending) {
        return;
      }
      if (pending.stats) {
        handlers.applyStats(pending.stats);
      }
      if (pending.health) {
        handlers.applyHealth(pending.health);
      }
      pending = null;
      clearMirrorIfRealPanelMounted();
    };

    window.__MYRM_E2E_WIKI__ = {
      inject: (payload) => {
        setMirror(payload);
        const applyNow = () => {
          if (!handlers) {
            pending = payload;
            return false;
          }
          if (payload.stats) {
            handlers.applyStats(payload.stats);
          }
          if (payload.health) {
            handlers.applyHealth(payload.health);
          }
          return true;
        };
        if (applyNow()) {
          window.requestAnimationFrame(() => {
            applyNow();
            clearMirrorIfRealPanelMounted();
          });
        }
      },
      isHandlersReady: () => handlers !== null,
      registerHandlers: (nextHandlers) => {
        handlers = nextHandlers;
        flushPending();
        window.setTimeout(flushPending, 0);
        window.setTimeout(flushPending, 250);
      },
      unregisterHandlers: () => {
        handlers = null;
      },
    };

    window.__MYRM_E2E_MIGRATION__ = {
      showCodexCompletionLane: (payload) => {
        setCodexCompletion(payload);
      },
      clearCodexCompletionLane: () => {
        setCodexCompletion(null);
      },
    };

    return () => {
      delete window.__MYRM_E2E_WIKI__;
      delete window.__MYRM_E2E_MIGRATION__;
    };
  }, []);

  return (
    <>
      {mirror ? <WikiE2eMirror payload={mirror} /> : null}
      {codexCompletion ? <CodexCompletionMirror payload={codexCompletion} /> : null}
    </>
  );
}
