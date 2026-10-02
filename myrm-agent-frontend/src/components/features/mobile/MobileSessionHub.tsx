'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  IconActivity,
  IconArrowRight,
  IconCheckCircle,
  IconChevronUp,
  IconClock,
  IconPlus,
  IconUsers,
} from '@/components/features/icons/PremiumIcons';
import { scheduleMobilePairRefresh, storeMobilePairToken } from '@/lib/mobileRemote';
import { useE2EEStatus } from '@/lib/e2ee/useE2EEStatus';
import E2EESecurityPanel from '@/components/features/e2ee/E2EESecurityPanel';
import { isImeComposing } from '@/lib/utils/imeUtils';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import type { ActiveSession, RecentSession } from '@/services/agent';
import { remoteAccessService } from '@/services/remoteAccess';
import type { SpawnOptionAgent, SpawnOptionProject } from '@/services/remoteAccess';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';

const AUTOSTART_SESSION_KEY = 'myrm_mobile_autostart_message';

function agentDisplayName(agentId: string | null, agentName: string | null, fallback: string, locale: string): string {
  return getBuiltinAgentName(agentId ?? '', agentName ?? fallback, locale);
}

export default function MobileSessionHub() {
  const t = useTranslations('mobileHub');
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const pairToken = searchParams.get('pair') ?? undefined;
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const [slots, setSlots] = useState<{ max: number; available: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openingChatId, setOpeningChatId] = useState<string | null>(null);
  const e2ee = useE2EEStatus();

  const [formOpen, setFormOpen] = useState(false);
  const [agents, setAgents] = useState<SpawnOptionAgent[]>([]);
  const [projects, setProjects] = useState<SpawnOptionProject[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [taskMessage, setTaskMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [optionsLoaded, setOptionsLoaded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const slotsFull = slots !== null && slots.available <= 0;

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await remoteAccessService.getMobileSessions(pairToken);
      setSessions(data.activeSessions ?? []);
      setRecentSessions(data.recentSessions ?? []);
      setSlots({ max: data.maxConcurrent ?? 0, available: data.availableSlots ?? 0 });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadFailed'));
      setSessions([]);
      setRecentSessions([]);
      setSlots(null);
    } finally {
      setLoading(false);
    }
  }, [pairToken, t]);

  useEffect(() => scheduleMobilePairRefresh(), []);

  useEffect(() => {
    void loadSessions();
    const timer = window.setInterval(() => void loadSessions(), 5000);
    return () => window.clearInterval(timer);
  }, [loadSessions]);

  const loadSpawnOptions = useCallback(async () => {
    if (optionsLoaded) {
      return;
    }
    try {
      const opts = await remoteAccessService.getSpawnOptions();
      setAgents(opts.agents);
      setProjects(opts.projects);
      if (opts.defaultAgentId) {
        setSelectedAgentId(opts.defaultAgentId);
      } else if (opts.agents.length > 0) {
        setSelectedAgentId(opts.agents[0].id);
      }
      setOptionsLoaded(true);
    } catch {
      setError(t('loadOptionsFailed'));
    }
  }, [optionsLoaded, t]);

  const handleToggleForm = useCallback(() => {
    const nextOpen = !formOpen;
    setFormOpen(nextOpen);
    if (nextOpen) {
      void loadSpawnOptions();
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }, [formOpen, loadSpawnOptions]);

  const handleSubmit = useCallback(async () => {
    const text = taskMessage.trim();
    if (!text || !selectedAgentId || slotsFull) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await remoteAccessService.spawnMobileSession({
        agentId: selectedAgentId,
        projectId: selectedProjectId || undefined,
        initialMessage: text,
      });
      storeMobilePairToken(result.token);
      sessionStorage.setItem(AUTOSTART_SESSION_KEY, text);
      setTaskMessage('');
      setFormOpen(false);
      router.push(result.mobilePath);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('spawnFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [taskMessage, selectedAgentId, selectedProjectId, slotsFull, router, t]);

  const openSession = useCallback(
    async (chatId: string) => {
      setOpeningChatId(chatId);
      setError(null);
      try {
        const { token, mobilePath } = await remoteAccessService.createPairingToken(chatId);
        storeMobilePairToken(token);
        router.push(mobilePath);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('openFailed'));
        setOpeningChatId(null);
      }
    },
    [router, t],
  );

  const usedSlots = slots ? Math.max(0, slots.max - slots.available) : sessions.length;
  const maxSlots = slots?.max ?? 0;
  const sectionsVisible = sessions.length > 0 || recentSessions.length > 0;

  return (
    <main className="min-h-dvh bg-gradient-to-b from-background via-background to-muted/30 text-foreground">
      <div className="mx-auto flex w-full max-w-lg flex-col gap-5 px-4 py-8 sm:px-6">
        <header className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
            <IconActivity className="h-3.5 w-3.5 text-primary" />
            {t('badge')}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t('title')}</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">{t('subtitle')}</p>
          <E2EESecurityPanel {...e2ee} />
        </header>

        {loading && sessions.length === 0 && recentSessions.length === 0 ? (
          <div className="rounded-2xl border border-border/70 bg-card/70 px-4 py-8 text-center text-sm text-muted-foreground backdrop-blur">
            {t('loading')}
          </div>
        ) : null}

        {error ? (
          <div className="rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {!loading && !error && !sectionsVisible ? (
          <div className="rounded-2xl border border-dashed border-border/80 bg-card/50 px-4 py-10 text-center text-sm text-muted-foreground">
            {t('empty')}
          </div>
        ) : null}

        {sectionsVisible ? (
          <>
            <section className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <IconActivity className="h-4 w-4 text-primary" />
                  {t('sectionActive')}
                </h2>
                {slots ? (
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                      slotsFull ? 'bg-destructive/10 text-destructive' : 'bg-secondary text-muted-foreground'
                    }`}
                  >
                    <IconUsers className="h-3 w-3" />
                    {t('slotsBadge', { used: usedSlots, max: maxSlots })}
                  </span>
                ) : null}
              </div>

              {sessions.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-border/80 bg-card/50 px-4 py-6 text-center text-sm text-muted-foreground">
                  {t('activeEmpty')}
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {sessions.map((session) => (
                    <li key={session.chatId}>
                      <button
                        type="button"
                        onClick={() => void openSession(session.chatId)}
                        disabled={openingChatId === session.chatId}
                        aria-label={agentDisplayName(session.agentId, session.agentName, session.agentType, locale)}
                        className="group block w-full rounded-2xl border border-border/70 bg-card/80 p-4 text-left shadow-sm backdrop-blur transition-all hover:border-primary/40 hover:bg-accent/30 disabled:cursor-wait disabled:opacity-70"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 space-y-1">
                            <p className="truncate text-sm font-semibold text-foreground">
                              {agentDisplayName(session.agentId, session.agentName, session.agentType, locale)}
                            </p>
                            <p className="truncate font-mono text-[11px] text-muted-foreground">{session.chatId}</p>
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                              {openingChatId === session.chatId
                                ? t('opening')
                                : t('elapsed', { seconds: session.elapsedSeconds })}
                            </span>
                            <IconArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="space-y-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconCheckCircle className="h-4 w-4 text-primary" />
                {t('sectionRecent')}
              </h2>
              {recentSessions.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-border/80 bg-card/50 px-4 py-6 text-center text-sm text-muted-foreground">
                  {t('recentEmpty')}
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {recentSessions.map((chat) => (
                    <li key={chat.chatId}>
                      <button
                        type="button"
                        onClick={() => void openSession(chat.chatId)}
                        disabled={openingChatId === chat.chatId}
                        aria-label={chat.title || chat.chatId}
                        className="group block w-full rounded-2xl border border-border/70 bg-card/80 p-4 text-left shadow-sm backdrop-blur transition-all hover:border-primary/40 hover:bg-accent/30 disabled:cursor-wait disabled:opacity-70"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 space-y-1">
                            <p className="truncate text-sm font-semibold text-foreground">
                              {chat.title || chat.chatId}
                            </p>
                            <p className="truncate text-[11px] text-muted-foreground">
                              {agentDisplayName(chat.agentId, chat.agentName, t('agentFallback'), locale)}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <span className="inline-flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                              <IconClock className="h-3 w-3" />
                              {formatRelativeTime(chat.updatedAt, locale)}
                            </span>
                            <IconArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}

        <section className="space-y-3">
          <button
            type="button"
            onClick={handleToggleForm}
            className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-primary/40 bg-primary/5 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
          >
            {formOpen ? (
              <>
                <IconChevronUp className="h-4 w-4" />
                {t('newTaskCollapse')}
              </>
            ) : (
              <>
                <IconPlus className="h-4 w-4" />
                {t('newTask')}
              </>
            )}
          </button>

          {formOpen && (
            <div className="space-y-3 rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur animate-in slide-in-from-top-2 duration-200">
              {slotsFull ? (
                <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs leading-relaxed text-destructive">
                  {t('slotsFull')}
                </p>
              ) : null}

              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-muted-foreground">{t('selectAgent')}</span>
                <select
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                  aria-label={t('selectAgent')}
                  className="block w-full rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
                >
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {getBuiltinAgentName(a.id, a.name, locale)}
                    </option>
                  ))}
                </select>
              </label>

              {projects.length > 0 && (
                <label className="block space-y-1.5">
                  <span className="text-xs font-medium text-muted-foreground">{t('selectProject')}</span>
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    aria-label={t('selectProject')}
                    className="block w-full rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
                  >
                    <option value="">{t('noProject')}</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-muted-foreground">{t('taskDescription')}</span>
                <textarea
                  ref={textareaRef}
                  value={taskMessage}
                  onChange={(e) => setTaskMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (isImeComposing(e)) {
                      return;
                    }
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      void handleSubmit();
                    }
                  }}
                  placeholder={t('taskPlaceholder')}
                  rows={3}
                  className="block w-full resize-none rounded-xl border bg-secondary/50 px-3 py-2.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/20"
                />
              </label>

              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={submitting || !taskMessage.trim() || !selectedAgentId || slotsFull}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? t('submitting') : t('submit')}
              </button>
            </div>
          )}
        </section>

        <p className="text-center text-[11px] text-muted-foreground">{t('footer')}</p>
      </div>
    </main>
  );
}
