'use client';

/**
 * [INPUT]
 * - fetchSessionMapProjects, fetchFleetCockpitSummary from @/services/sessionMap
 * - SessionMapGraph from ./SessionMapGraph
 * - AgentFleetCockpit from ./AgentFleetCockpit
 * - SessionContextJumpModal from ./SessionContextJumpModal
 * - Translation strings from 'sessionMap' namespace
 * - Global event 'myrm:open-session-map'
 *
 * [OUTPUT]
 * - SessionMapTrigger: Floating HUD capsule & full-screen 2D session map modal cockpit
 *
 * [POS]
 * HUD entrance and full-screen view orchestrator for Project-Centric Session Map and Fleet Management.
 * Strict typing: Zero `any`. File length < 360 lines. Zero native emoji.
 */

import { useState, useEffect, useCallback, useId } from 'react';
import { useTranslations } from 'next-intl';
import { IconActivity, IconX, IconFolder } from '@/components/features/icons/PremiumIcons';
import {
  fetchSessionMapProjects,
  fetchFleetCockpitSummary,
  type ProjectCluster,
  type SessionNode,
  type FleetCockpitSummary,
  type AgentState,
} from '@/services/sessionMap';
import { SessionMapGraph } from './SessionMapGraph';
import { AgentFleetCockpit } from './AgentFleetCockpit';
import { SessionContextJumpModal } from './SessionContextJumpModal';

interface SessionMapTriggerProps {
  /** 菜单内使用时只保留快捷键/事件监听与地图弹层。 */
  showTrigger?: boolean;
}

export function SessionMapTrigger({ showTrigger = true }: SessionMapTriggerProps = {}) {
  const t = useTranslations('sessionMap');
  const dialogTitleId = useId();

  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [clusters, setClusters] = useState<ProjectCluster[]>([]);
  const [summary, setSummary] = useState<FleetCockpitSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [activeFilter, setActiveFilter] = useState<AgentState | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [viewMode, setViewMode] = useState<'topology' | 'list'>('topology');

  // Selected session for jump modal
  const [selectedSession, setSelectedSession] = useState<SessionNode | null>(null);
  const [selectedProject, setSelectedProject] = useState<ProjectCluster | null>(null);
  const [isJumpModalOpen, setIsJumpModalOpen] = useState<boolean>(false);

  // Load topology and cockpit summary data
  const loadData = useCallback(async (filter?: AgentState) => {
    setIsLoading(true);
    try {
      const [projData, sumData] = await Promise.all([fetchSessionMapProjects(filter), fetchFleetCockpitSummary()]);
      setClusters(projData);
      setSummary(sumData);
    } catch {
      // Graceful fallback
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadData(activeFilter);
    }
  }, [isOpen, activeFilter, loadData]);

  // Global hotkey (Cmd+Shift+M / Ctrl+Shift+M) & custom event listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === 'Escape' && isOpen && !isJumpModalOpen) {
        setIsOpen(false);
      }
    };

    const handleCustomOpen = () => setIsOpen(true);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('myrm:open-session-map', handleCustomOpen);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('myrm:open-session-map', handleCustomOpen);
    };
  }, [isOpen, isJumpModalOpen]);

  const handleSelectSession = useCallback((session: SessionNode, project: ProjectCluster) => {
    setSelectedSession(session);
    setSelectedProject(project);
    setIsJumpModalOpen(true);
  }, []);

  const handleJumpIn = useCallback((sessionId: string) => {
    // Dispatch navigation event to activate target chat
    const event = new CustomEvent('myrm:open-chat-session', {
      detail: { sessionId },
    });
    window.dispatchEvent(event);
    setIsOpen(false);
  }, []);

  return (
    <>
      {/* Floating HUD Capsule Trigger */}
      {showTrigger && (
        <aside
          data-session-map-ignore="true"
          aria-label={t('hudAriaLabel')}
          className="fixed bottom-6 right-48 z-[9985] flex items-center select-none"
        >
          <button
            type="button"
            onClick={() => setIsOpen((prev) => !prev)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-medium shadow-xl backdrop-blur-md transition-all border ${
              isOpen
                ? 'bg-primary text-primary-foreground border-primary ring-2 ring-primary/40'
                : 'bg-card/90 text-foreground border-border/80 hover:bg-card hover:border-primary/50'
            }`}
            title={t('toggleHint')}
          >
            <IconActivity className="w-4 h-4 text-emerald-500 animate-pulse" />
            <span>{isOpen ? t('hudActive') : t('hudTrigger')}</span>
            <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-background/60 border border-border/40 text-muted-foreground">
              {t('shortcutHint')}
            </kbd>
          </button>
        </aside>
      )}

      {/* Full-screen 2D Session Map Modal Cockpit */}
      {isOpen && (
        <div className="fixed inset-0 z-[9995] flex items-center justify-center bg-black/70 backdrop-blur-md p-4 sm:p-6">
          <dialog
            open
            aria-modal="true"
            aria-labelledby={dialogTitleId}
            className="w-full max-w-6xl max-h-[92vh] rounded-3xl bg-card border border-border shadow-2xl p-5 sm:p-6 text-foreground flex flex-col gap-4 m-0 overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border/60 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
                  <IconActivity className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h2 id={dialogTitleId} className="text-base font-semibold">
                    {t('modalTitle')}
                  </h2>
                  <p className="text-xs text-muted-foreground">{t('modalSubtitle')}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label={t('closeAriaLabel')}
              >
                <IconX className="w-5 h-5" />
              </button>
            </div>

            {/* Fleet Metrics Cockpit Header */}
            <AgentFleetCockpit
              summary={summary}
              activeFilter={activeFilter}
              onFilterChange={setActiveFilter}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />

            {/* Main Content Area */}
            <div className="flex-1 min-h-[480px] overflow-y-auto">
              {isLoading ? (
                <div className="w-full h-80 flex items-center justify-center text-xs text-muted-foreground">
                  {t('loadingTopology')}
                </div>
              ) : viewMode === 'topology' ? (
                <SessionMapGraph
                  clusters={clusters}
                  selectedSessionId={selectedSession?.id}
                  onSelectSession={handleSelectSession}
                  stateFilter={activeFilter}
                  searchQuery={searchQuery}
                />
              ) : (
                /* Compact List View */
                <div className="flex flex-col gap-4 p-2">
                  {clusters.map((proj) => (
                    <div
                      key={proj.id}
                      className="p-4 rounded-2xl bg-muted/30 border border-border/60 flex flex-col gap-2.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-semibold text-sm">
                          <IconFolder className="w-4 h-4 text-primary" />
                          <span>{proj.name}</span>
                          <span className="text-xs font-mono text-muted-foreground">
                            ({proj.workspace_path || 'default'})
                          </span>
                        </div>
                        <span className="text-xs font-mono text-muted-foreground">{proj.sessions.length} sessions</span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                        {proj.sessions.map((sess) => (
                          <button
                            key={sess.id}
                            type="button"
                            onClick={() => handleSelectSession(sess, proj)}
                            className="p-3 rounded-xl bg-card border border-border/60 hover:border-primary/60 text-left transition-colors flex flex-col gap-1.5"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium truncate">{sess.title}</span>
                              <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-muted">
                                {sess.state}
                              </span>
                            </div>
                            <span className="text-[10px] font-mono text-muted-foreground">
                              {sess.agent_name} · {Math.round(sess.tokens_used / 1000)}k tokens
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </dialog>
        </div>
      )}

      {/* Jump In Replay Modal */}
      <SessionContextJumpModal
        isOpen={isJumpModalOpen}
        onClose={() => setIsJumpModalOpen(false)}
        session={selectedSession}
        project={selectedProject}
        onJumpIn={handleJumpIn}
      />
    </>
  );
}
