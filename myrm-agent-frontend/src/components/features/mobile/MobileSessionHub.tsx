'use client';

/**
 * [INPUT]
 * - remoteAccessService (sessions, spawn-options, pairing token)
 * - useMobileViewportAdapter & MobileShellStatusBar (native shell perception)
 * - MobileHostControlRoster & MobilePwaInstallGuide (parity pack controls)
 *
 * [OUTPUT]
 * - MobileSessionHub: Complete native mobile shell parity control hub (< 370 lines)
 *
 * [POS]
 * Mobile PWA thin-client primary landing hub with dual-zone sessions, quick capture, and shell perception.
 */

import { useRouter, useSearchParams } from 'next/navigation';
import { useLocale, useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';
import {
  IconActivity,
  IconArrowRight,
  IconCheckCircle,
  IconClock,
  IconUsers,
  IconX,
  IconShieldCheck,
} from '@/components/features/icons/PremiumIcons';
import { scheduleMobilePairRefresh, storeMobilePairToken } from '@/lib/mobileRemote';
import { useE2EEStatus } from '@/lib/e2ee/useE2EEStatus';
import E2EESecurityPanel from '@/components/features/e2ee/E2EESecurityPanel';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import { cancelActiveChatAgent } from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import type { ActiveSession, RecentSession, CurtainStatus } from '@/services/agent';
import { remoteAccessService } from '@/services/remoteAccess';
import type { SpawnOptionAgent, SpawnOptionProject } from '@/services/remoteAccess';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import MobileQuickCaptureDrawer from './MobileQuickCaptureDrawer';
import { MobileQuickCaptureFab } from './MobileQuickCaptureFab';
import { useMobileViewportAdapter } from './useMobileViewportAdapter';
import { MobileShellStatusBar } from './MobileShellStatusBar';
import { MobileHostControlRoster } from './MobileHostControlRoster';
import { MobilePwaInstallGuide } from './MobilePwaInstallGuide';
import { MobileTaskSpawnForm } from './MobileTaskSpawnForm';

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

  const { isStandalone } = useMobileViewportAdapter();
  const e2ee = useE2EEStatus();

  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const [slots, setSlots] = useState<{ max: number; available: number } | null>(null);
  const [curtain, setCurtain] = useState<CurtainStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openingChatId, setOpeningChatId] = useState<string | null>(null);
  const [stoppingChatId, setStoppingChatId] = useState<string | null>(null);

  const [agents, setAgents] = useState<SpawnOptionAgent[]>([]);
  const [projects, setProjects] = useState<SpawnOptionProject[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [taskMessage, setTaskMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [optionsLoaded, setOptionsLoaded] = useState(false);
  const [captureDrawerOpen, setCaptureDrawerOpen] = useState(false);

  const slotsFull = slots !== null && slots.available <= 0;

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await remoteAccessService.getMobileSessions(pairToken);
      setSessions(data.activeSessions ?? []);
      setRecentSessions(data.recentSessions ?? []);
      setSlots({ max: data.maxConcurrent ?? 0, available: data.availableSlots ?? 0 });
      setCurtain(data.curtain ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('loadFailed'));
      setSessions([]);
      setRecentSessions([]);
      setSlots(null);
      setCurtain(null);
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

  const handleConvertToTask = useCallback(
    (content: string) => {
      setTaskMessage(content);
      void loadSpawnOptions();
    },
    [loadSpawnOptions],
  );

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

  const stopSession = useCallback(
    async (chatId: string) => {
      setStoppingChatId(chatId);
      try {
        await cancelActiveChatAgent(chatId);
        showI18nToast('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
        await loadSessions();
      } catch {
        showI18nToast('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
      } finally {
        setStoppingChatId(null);
      }
    },
    [loadSessions],
  );

  const usedSlots = slots ? Math.max(0, slots.max - slots.available) : sessions.length;
  const maxSlots = slots?.max ?? 0;
  const sectionsVisible = sessions.length > 0 || recentSessions.length > 0;

  return (
    <main className="min-h-dvh bg-gradient-to-b from-background via-background to-muted/30 text-foreground">
      <MobileShellStatusBar
        isConnecting={loading}
        hasError={Boolean(error)}
        onRetry={() => void loadSessions()}
        hostName="Myrm Host"
        isStandalone={isStandalone}
      />

      <div className="mx-auto flex w-full max-w-lg flex-col gap-5 px-4 pt-12 pb-24 sm:px-6">
        <header className="space-y-2">
          <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
            <IconActivity className="h-3.5 w-3.5 text-primary" />
            {t('badge')}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t('title')}</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">{t('subtitle')}</p>
          {curtain?.available && curtain.active ? (
            <output
              data-testid="curtain-shield-badge"
              className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
              aria-live="polite"
            >
              <IconShieldCheck className="h-3.5 w-3.5" />
              {t('curtainActive')}
            </output>
          ) : null}
          <E2EESecurityPanel {...e2ee} />
        </header>

        <MobileHostControlRoster
          agents={agents}
          activeSessions={sessions}
          selectedAgentId={selectedAgentId}
          onSelectAgent={(id) => setSelectedAgentId(id)}
        />

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
                      <div className="group rounded-2xl border border-border/70 bg-card/80 p-4 shadow-sm backdrop-blur transition-all hover:border-primary/40 hover:bg-accent/30">
                        <button
                          type="button"
                          onClick={() => void openSession(session.chatId)}
                          disabled={openingChatId === session.chatId}
                          aria-label={agentDisplayName(session.agentId, session.agentName, session.agentType, locale)}
                          className="block w-full text-left disabled:cursor-wait disabled:opacity-70"
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
                        <div className="mt-3 flex items-center justify-end border-t border-border/50 pt-3">
                          <button
                            type="button"
                            onClick={() => void stopSession(session.chatId)}
                            disabled={stoppingChatId === session.chatId}
                            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-60"
                          >
                            <IconX className="h-3 w-3" />
                            {stoppingChatId === session.chatId ? t('stopping') : t('stop')}
                          </button>
                        </div>
                      </div>
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

        <MobileTaskSpawnForm
          agents={agents}
          projects={projects}
          slotsFull={slotsFull}
          submitting={submitting}
          selectedAgentId={selectedAgentId}
          onSelectAgent={(id) => setSelectedAgentId(id)}
          selectedProjectId={selectedProjectId}
          onSelectProject={(id) => setSelectedProjectId(id)}
          taskMessage={taskMessage}
          onTaskMessageChange={(msg) => setTaskMessage(msg)}
          onSubmit={handleSubmit}
          onOpenOptions={() => void loadSpawnOptions()}
        />

        <p className="text-center text-[11px] text-muted-foreground">{t('footer')}</p>
      </div>

      <MobileQuickCaptureFab onClick={() => setCaptureDrawerOpen(true)} />
      <MobileQuickCaptureDrawer
        open={captureDrawerOpen}
        onClose={() => setCaptureDrawerOpen(false)}
        onConvertToTask={handleConvertToTask}
      />
      <MobilePwaInstallGuide />
    </main>
  );
}
