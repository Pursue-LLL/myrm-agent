'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import { API_BASE_URL } from '@/lib/api';
import { normalizeApprovalPayload } from '@/store/useApprovalStore';
import useConfigStore from '@/store/useConfigStore';
import { notificationService } from '@/services/notification';
import { useBudgetExceededStore } from '@/store/useBudgetExceededStore';
import { mutate as mutateSwr } from 'swr';

import { showMemoryOperationToasts } from '@/hooks/globalEvents/memoryOperationToasts';
import { showLocatorHealedToast } from '@/hooks/globalEvents/locatorHealedToast';

interface SSEPayload {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

const SSE_URL = `${API_BASE_URL}/notifications/stream`;
const BC_CHANNEL = 'myrm-sse-events';
const LEADER_KEY = 'myrm-sse-leader';
const HEARTBEAT_INTERVAL = 3_000;
const HEARTBEAT_TIMEOUT = 6_000;

const PASSTHROUGH_EVENTS: ReadonlySet<string> = new Set([
  'memory_history_updated',
  'subagents_updated',
  'teammate_message',
  'cron_updated',
  'skill_ab_test_updated',
  'health_status_updated',
  'budget_updated',
  'channel_status_updated',
  'skill_quality_updated',
  'goal:branch_switched',
]);

/**
 * Cross-tab SSE sharing via BroadcastChannel + leader election.
 * Only the leader tab maintains the actual EventSource connection;
 * followers receive events through BroadcastChannel, avoiding
 * HTTP/1.1 connection pool exhaustion when multiple tabs are open.
 */
export function useGlobalEvents(): void {
  const router = useRouter();
  const t = useTranslations('notifications');
  const enabled = useConfigStore((s) => s.enableWebNotifications);
  const sourceRef = useRef<EventSource | null>(null);
  const isLeaderRef = useRef(false);
  const retryRef = useRef(0);
  const tabId = useRef(crypto.randomUUID());
  const debouncedRefetches = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    if (!enabled) {
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }

    const bc = new BroadcastChannel(BC_CHANNEL);
    let disposed = false;
    let reconciling = false;
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

    function notifyIfLeader(title: string, body?: string, onClick?: () => void) {
      if (isLeaderRef.current) {
        notificationService.notify(title, { body, fallbackToToast: false, onClick });
      }
    }

    function handleEvent(payload: SSEPayload) {
      const openSkillGrowth = () => router.push('/settings/evolutionPending');

      if (payload.type === 'pairing_pending') {
        const channel = String(payload.data.channel ?? '');
        const displayName = payload.data.display_name ? String(payload.data.display_name) : '';
        const sender = displayName || String(payload.data.sender_id ?? '');
        toast.info(t('pairingPending', { channel, sender }), {
          id: 'pairing-pending',
          duration: 30_000,
          dismissible: true,
          action: {
            label: t('goToApproval'),
            onClick: () => {
              toast.dismiss('pairing-pending');
              router.push('/settings/channels');
            },
          },
        });
        window.dispatchEvent(new CustomEvent('pairings-updated'));
      } else if (payload.type === 'config_health_warning') {
        const missingItems = Array.isArray(payload.data.missing_items)
          ? payload.data.missing_items.map((item) => String(item))
          : undefined;
        const itemsText = missingItems?.join(', ') || 'LLM provider';
        toast.warning(t('configHealthWarning', { items: itemsText }), {
          duration: 10_000,
          dismissible: true,
          action: {
            label: t('goToSettings'),
            onClick: () => router.push('/settings/models'),
          },
        });
      } else if (payload.type === 'channel_connected' || payload.type === 'channel_disconnected') {
        window.dispatchEvent(
          new CustomEvent('channel-status-change', {
            detail: {
              channel: String(payload.data.channel ?? ''),
              status: String(payload.data.status ?? ''),
              type: payload.type,
            },
          }),
        );
      } else if (payload.type === 'groups_updated') {
        window.dispatchEvent(
          new CustomEvent('groups-updated', {
            detail: {
              channel: String(payload.data.channel ?? ''),
              count: Number(payload.data.count ?? 0),
            },
          }),
        );
      } else if (payload.type === 'message_dead_lettered') {
        const channel = String(payload.data.channel ?? 'unknown');
        const reason = String(payload.data.error_reason ?? 'Unknown error');
        toast.error(t('messageDeadLettered', { channel, reason }), {
          duration: 10_000,
          dismissible: true,
        });
        notifyIfLeader(t('messageDeadLettered', { channel, reason }), reason);
        window.dispatchEvent(new CustomEvent('message_dead_lettered'));
      } else if (payload.type === 'approval_required') {
        const actionType = String(payload.data.action_type ?? 'unknown');
        const normalizedApproval = normalizeApprovalPayload(payload.data);
        const openApprovalDialog = () => {
          import('@/store/useApprovalStore').then((mod) => {
            mod.default.getState().openApproval(normalizedApproval);
          });
        };
        toast.info(t('approvalRequired', { actionType }), {
          duration: 8_000,
          dismissible: true,
          action: {
            label: t('reviewApproval'),
            onClick: openApprovalDialog,
          },
        });
        notifyIfLeader(t('approvalRequired', { actionType }), actionType, openApprovalDialog);
        window.dispatchEvent(
          new CustomEvent('approval-required', {
            detail: normalizedApproval,
          }),
        );
      } else if (payload.type === 'approval_resolved') {
        const approvalId = String(payload.data.approval_id ?? '');
        if (approvalId) {
          import('@/store/useApprovalStore').then((mod) => {
            mod.default.getState().closeApproval(approvalId);
          });
        }
        window.dispatchEvent(new CustomEvent('approval_resolved', { detail: payload.data }));
      } else if (payload.type === 'new_skill_draft') {
        const name = String(payload.data.name ?? '');
        toast.info(t('newSkillDraft', { name }), {
          duration: 8_000,
          dismissible: true,
          action: {
            label: t('reviewDraft'),
            onClick: openSkillGrowth,
          },
        });
        window.dispatchEvent(
          new CustomEvent('skill-draft-created', {
            detail: {
              draftId: String(payload.data.draft_id ?? ''),
              name,
              draftType: String(payload.data.draft_type ?? ''),
            },
          }),
        );
      } else if (payload.type === 'skill_growth_updated') {
        const name = String(payload.data.name ?? '');
        const status = String(payload.data.status ?? '');

        if (status === 'AUTO_APPLIED') {
          toast.success(t('skillGrowthAutoApplied', { name }), {
            duration: 8_000,
            dismissible: true,
            action: {
              label: t('openSkillGrowth'),
              onClick: openSkillGrowth,
            },
          });
        } else if (status === 'FAILED_SCAN') {
          toast.error(t('skillGrowthFailedScan', { name }), {
            duration: 10_000,
            dismissible: true,
            action: {
              label: t('openSkillGrowth'),
              onClick: openSkillGrowth,
            },
          });
        } else if (status === 'BLOCKED_LOCKED') {
          toast.warning(t('skillGrowthBlockedLocked', { name }), {
            duration: 10_000,
            dismissible: true,
            action: {
              label: t('openSkillGrowth'),
              onClick: openSkillGrowth,
            },
          });
        }

        window.dispatchEvent(
          new CustomEvent('skill-growth-updated', {
            detail: {
              caseId: String(payload.data.case_id ?? ''),
              status,
              draftType: String(payload.data.draft_type ?? ''),
              name,
            },
          }),
        );
      } else if (payload.type === 'skill_evolved') {
        const skillName = String(payload.data.skill_name ?? '');
        const evolutionType = String(payload.data.evolution_type ?? 'new');
        const description = String(payload.data.description ?? '');
        const evolutionId = String(payload.data.evolution_id ?? '');

        const doRollback = async () => {
          if (!evolutionId) return;
          try {
            const res = await fetch(`/api/v1/evolution/history/${evolutionId}/rollback`, { method: 'POST' });
            if (!res.ok) throw new Error('Rollback failed');
            toast.success(t('rollbackSuccess', { name: skillName }));
          } catch {
            toast.error(t('rollbackFailed', { name: skillName }));
          }
        };

        toast.success(
          evolutionType === 'new'
            ? t('skillEvolvedNew', { name: skillName })
            : t('skillEvolvedPatch', { name: skillName }),
          {
            description,
            duration: 8_000,
            dismissible: true,
            action: {
              label: t('openSkillGrowth'),
              onClick: openSkillGrowth,
            },
            cancel: evolutionId
              ? {
                  label: t('undoEvolve') || 'Undo',
                  onClick: doRollback,
                }
              : undefined,
          },
        );
        window.dispatchEvent(
          new CustomEvent('skill-evolved', {
            detail: { skill_name: skillName, evolution_type: evolutionType },
          }),
        );
      } else if (payload.type === 'idle_status') {
        window.dispatchEvent(
          new CustomEvent('idle-status', {
            detail: payload.data,
          }),
        );
      } else if (payload.type === 'system_notification') {
        const title = String(payload.data.title ?? '系统通知');
        const message = String(payload.data.message ?? '');
        const meta = asRecord(payload.data.meta_data);
        const metaCount = typeof meta.count === 'number' ? meta.count : 0;
        const subsumedIds = Array.isArray(meta.subsumed_ids) ? meta.subsumed_ids : [];

        let cancelObj = undefined;
        if (meta.type === 'cognitive_consolidation' && metaCount > 0 && subsumedIds.length > 0) {
          cancelObj = {
            label: t('undoConsolidation') || 'Undo (撤销)',
            onClick: async () => {
              try {
                const res = await fetch(`/api/memory/undo-consolidation`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ subsumed_ids: subsumedIds }),
                });
                if (!res.ok) throw new Error('Undo failed');
                toast.success(t('undoConsolidationSuccess') || '已恢复被降维擦除的记忆');
              } catch {
                toast.error(t('undoConsolidationFailed') || '恢复记忆失败，请稍后重试');
              }
            },
          };
        }

        // Dispatch a custom event so specific components (like ChatWindow) can handle it
        window.dispatchEvent(new CustomEvent('system-notification', { detail: payload }));

        // Only show global toast if it's not a snapshot_created event
        // (snapshot_created is handled specifically by ChatWindow with a custom icon)
        if (meta.type !== 'snapshot_created') {
          toast.success(title, {
            description: message,
            duration: 10_000,
            dismissible: true,
            cancel: cancelObj,
          });
        }
      } else if (payload.type === 'memory_operation') {
        showMemoryOperationToasts(payload.data, { t, router });
        window.dispatchEvent(new CustomEvent(payload.type, { detail: payload.data }));
      } else if (payload.type === 'locator_healed') {
        showLocatorHealedToast(payload.data);
        window.dispatchEvent(new CustomEvent(payload.type, { detail: payload.data }));
      } else if (PASSTHROUGH_EVENTS.has(payload.type)) {
        window.dispatchEvent(new CustomEvent(payload.type, { detail: payload.data }));
      } else if (payload.type === 'async_agent_stream_chunk') {
        window.dispatchEvent(
          new CustomEvent('async-agent-stream-chunk', {
            detail: payload.data,
          }),
        );
      } else if (payload.type === 'health_alert') {
        const component = String(payload.data.component ?? 'Unknown');
        const status = String(payload.data.status ?? 'fail');
        const message = String(payload.data.message ?? 'Health check failed');
        const technicalDetail = payload.data.detail ? String(payload.data.detail) : undefined;
        const fixSuggestion = payload.data.fix_suggestion ? String(payload.data.fix_suggestion) : undefined;
        const layer = String(payload.data.layer ?? 'system');

        const title = `${component} ${status === 'fail' ? 'Failed' : 'Warning'}`;

        if (status === 'fail') {
          toast.error(t('healthAlertFail', { component, layer }) || title, {
            description: `${message}${fixSuggestion ? `\nTip: ${fixSuggestion}` : ''}`,
            duration: 15_000,
            dismissible: true,
            action: {
              label: t('viewHealthDashboard') || 'View Dashboard',
              onClick: () => router.push('/settings/system'),
            },
          });
          notifyIfLeader(t('healthAlertFail', { component, layer }) || title, message, () =>
            router.push('/settings/system'),
          );
        } else if (status === 'warn') {
          toast.warning(t('healthAlertWarn', { component, layer }) || title, {
            description: `${message}${fixSuggestion ? `\nTip: ${fixSuggestion}` : ''}`,
            duration: 12_000,
            dismissible: true,
            action: {
              label: t('viewHealthDashboard') || 'View Dashboard',
              onClick: () => router.push('/settings/system'),
            },
          });
        }

        window.dispatchEvent(
          new CustomEvent('health-alert', {
            detail: { component, status, message, technicalDetail, fixSuggestion, layer },
          }),
        );
      } else if (payload.type === 'budget_alert') {
        const budgetStatus = String(payload.data.status ?? 'warning');
        const pct = typeof payload.data.pct === 'number' ? payload.data.pct : 0;
        const remaining = typeof payload.data.remaining === 'number' ? payload.data.remaining : 0;
        const dimension = String(payload.data.dimension ?? '');

        if (budgetStatus === 'exceeded') {
          if (dimension === 'work_units') {
            const required = typeof payload.data.today_cost === 'number' ? payload.data.today_cost : 0;
            const limit = typeof payload.data.daily_limit === 'number' ? payload.data.daily_limit : remaining;
            useBudgetExceededStore.getState().show(Math.round(required), Math.round(limit));
            void mutateSwr((key) => Array.isArray(key) && key[0] === 'cp-entitlements');
          } else {
            toast.error(t('budgetExceeded') || 'Budget exceeded', {
              description: `${dimension} — $${remaining.toFixed(4)} remaining`,
              duration: 15_000,
              dismissible: true,
            });
            notifyIfLeader(
              t('budgetExceeded') || 'Budget exceeded',
              `${dimension} — $${remaining.toFixed(4)} remaining`,
            );
          }
        } else if (budgetStatus === 'finalization') {
          toast.warning(t('budgetFinalization') || 'Budget nearly exhausted — finalizing', {
            description: `${dimension} — $${remaining.toFixed(4)} remaining`,
            duration: 12_000,
            dismissible: true,
          });
        } else {
          const ecoActive = payload.data.eco_mode === true;
          toast.warning(t('budgetWarning') || `Budget ${pct.toFixed(0)}% used`, {
            description: ecoActive
              ? `${dimension} — $${remaining.toFixed(4)} remaining\n${t('ecoModeActive') || 'Eco mode: compressing context to save tokens'}`
              : `${dimension} — $${remaining.toFixed(4)} remaining`,
            duration: 10_000,
            dismissible: true,
          });
        }

        window.dispatchEvent(new CustomEvent('budget_alert', { detail: payload.data }));
      } else if (payload.type === 'kanban_task_updated') {
        const kd = payload.data;
        const kAction = String(kd.action ?? '');
        const kStatus = String(kd.status ?? '');
        const kTitle = String(kd.title ?? kd.task_id ?? '');
        const kDetail = String(kd.detail ?? '');
        const isTerminal =
          kAction === 'task_completed' ||
          kAction === 'task_blocked' ||
          kAction === 'task_failed' ||
          (kAction === 'moved' && ['completed', 'blocked', 'failed'].includes(kStatus));

        if (isTerminal && kTitle) {
          const resolved = kStatus || kAction.replace('task_', '');
          const statusLabel =
            resolved === 'completed'
              ? t('kanbanTaskCompleted')
              : resolved === 'blocked'
                ? t('kanbanTaskBlocked')
                : t('kanbanTaskFailed');
          const desc = kDetail ? kDetail.slice(0, 200) : undefined;
          if (resolved === 'completed') {
            toast.success(`${statusLabel}: ${kTitle}`, { description: desc, duration: 8_000, dismissible: true });
          } else {
            toast.warning(`${statusLabel}: ${kTitle}`, { description: desc, duration: 10_000, dismissible: true });
          }
          notifyIfLeader(`${statusLabel}: ${kTitle}`, desc);
        }

        window.dispatchEvent(new CustomEvent('kanban-task-updated', { detail: payload.data }));
      } else if (payload.type === 'goal_terminal') {
        const status = String(payload.data.status ?? '');
        const objective = String(payload.data.objective ?? '').slice(0, 100);
        const sessionId = String(payload.data.session_id ?? '');
        const statusLabel =
          status === 'complete'
            ? t('goalCompleted') || 'Goal Completed'
            : status === 'cancelled'
              ? t('goalCancelled') || 'Goal Cancelled'
              : status === 'budget_limited'
                ? t('goalBudgetLimited') || 'Goal Budget Limited'
                : status === 'needs_human_review'
                  ? t('goalNeedsReview') || 'Goal Needs Review'
                  : t('goalTerminal') || 'Goal Finished';
        if (status === 'complete') {
          toast.success(statusLabel, { description: objective, duration: 8_000, dismissible: true });
        } else {
          toast.warning(statusLabel, { description: objective, duration: 10_000, dismissible: true });
        }
        const navigateToGoal = sessionId ? () => router.push(`/chat/${sessionId}`) : undefined;
        notifyIfLeader(statusLabel, objective, navigateToGoal);
      } else if (payload.type === 'goal_dequeued') {
        const objective = String(payload.data.objective ?? '').slice(0, 100);
        const dqSessionId = String(payload.data.session_id ?? '');
        const label = t('goalDequeued') || 'Next goal started';
        toast.info(label, { description: objective, duration: 6_000, dismissible: true });
        const navigateToDequeued = dqSessionId ? () => router.push(`/chat/${dqSessionId}`) : undefined;
        notifyIfLeader(label, objective, navigateToDequeued);
        if (dqSessionId) {
          import('@/store/chat/goals/useGoalStore').then(({ useGoalStore }) => {
            useGoalStore.getState().fetchQueue(dqSessionId);
          });
        }
      } else if (payload.type === 'agent_config_updated') {
        const agentId = String(payload.data.agent_id ?? '');
        const action = String(payload.data.action ?? 'updated');
        if (agentId && (action === 'updated' || action === 'rollback')) {
          if (action === 'rollback') {
            toast.success(t('rollbackSuccess') || 'Successfully rolled back agent profile.');
          }

          if (debouncedRefetches.current[agentId]) {
            clearTimeout(debouncedRefetches.current[agentId]);
          }
          debouncedRefetches.current[agentId] = setTimeout(() => {
            import('@/store/useAgentStore')
              .then((mod) => {
                const store = mod.default.getState();
                store.fetchAgents(1, 20, true);
                if (store.selectedAgent?.id === agentId) {
                  store.fetchAgent(agentId);
                }
              })
              .catch(() => {});
            delete debouncedRefetches.current[agentId];
          }, 500);
        }
        window.dispatchEvent(new CustomEvent('agent-config-updated', { detail: payload.data }));
      }
    }

    function connectSSE() {
      if (disposed || !isLeaderRef.current) return;
      sourceRef.current?.close();

      const es = new EventSource(SSE_URL);
      sourceRef.current = es;

      es.onopen = async () => {
        retryRef.current = 0;

        window.dispatchEvent(new CustomEvent('app_resync_required'));
        bc.postMessage({ kind: 'resync-pulse' });

        if (reconciling) return;
        reconciling = true;
        try {
          const storeModule = await import('@/store/useChatStore');
          const store = storeModule.default.getState();
          if (store.chatId) {
            storeModule.default.setState({ loading: true });
            try {
              await storeModule.default.getState().initializeChat(store.chatId);
            } finally {
              storeModule.default.setState({ loading: false });
            }
          }
        } finally {
          reconciling = false;
        }
      };

      es.onmessage = (ev: MessageEvent<string>) => {
        try {
          const payload: SSEPayload = JSON.parse(ev.data);
          bc.postMessage({ kind: 'sse-event', payload });
          handleEvent(payload);
        } catch {
          /* malformed */
        }
      };

      es.onerror = () => {
        es.close();
        sourceRef.current = null;
        if (disposed || !isLeaderRef.current) return;
        const delay = Math.min(1000 * 2 ** retryRef.current, 30_000);
        retryRef.current += 1;
        setTimeout(connectSSE, delay);
      };
    }

    function becomeLeader() {
      if (isLeaderRef.current) return;
      isLeaderRef.current = true;
      localStorage.setItem(LEADER_KEY, tabId.current);
      connectSSE();
      heartbeatTimer = setInterval(() => {
        bc.postMessage({ kind: 'heartbeat', tabId: tabId.current });
      }, HEARTBEAT_INTERVAL);
    }

    function stepDown() {
      isLeaderRef.current = false;
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      sourceRef.current?.close();
      sourceRef.current = null;
    }

    function resetWatchdog() {
      if (watchdogTimer) clearTimeout(watchdogTimer);
      watchdogTimer = setTimeout(() => {
        if (!disposed) becomeLeader();
      }, HEARTBEAT_TIMEOUT);
    }

    bc.onmessage = (ev: MessageEvent<{ kind: string; payload?: SSEPayload; tabId?: string }>) => {
      const msg = ev.data;
      if (msg.kind === 'sse-event' && msg.payload && !isLeaderRef.current) {
        handleEvent(msg.payload);
      } else if (msg.kind === 'resync-pulse' && !isLeaderRef.current) {
        window.dispatchEvent(new CustomEvent('app_resync_required'));
      } else if (msg.kind === 'heartbeat' && msg.tabId !== tabId.current) {
        if (isLeaderRef.current) stepDown();
        resetWatchdog();
      } else if (msg.kind === 'leader-claim' && msg.tabId !== tabId.current) {
        if (isLeaderRef.current) stepDown();
        resetWatchdog();
      }
    };

    const existingLeader = localStorage.getItem(LEADER_KEY);
    if (!existingLeader) {
      becomeLeader();
      bc.postMessage({ kind: 'leader-claim', tabId: tabId.current });
    } else {
      resetWatchdog();
      bc.postMessage({ kind: 'leader-claim', tabId: tabId.current });
      setTimeout(() => {
        if (!disposed && !isLeaderRef.current) {
          const current = localStorage.getItem(LEADER_KEY);
          if (!current || current === tabId.current) becomeLeader();
        }
      }, HEARTBEAT_TIMEOUT);
    }

    return () => {
      disposed = true;
      stepDown();
      if (watchdogTimer) clearTimeout(watchdogTimer);
      if (isLeaderRef.current) localStorage.removeItem(LEADER_KEY);
      bc.close();
      Object.values(debouncedRefetches.current).forEach(clearTimeout);
      debouncedRefetches.current = {};
    };
  }, [router, t, enabled]);
}
