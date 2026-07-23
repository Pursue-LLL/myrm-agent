/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * ./handlerDeps::useChatStore (POS: chat session store access)
 * @/store/chat/pendingGapRetry::flushPendingGapRetry (POS: deferred gap retry flush)
 *
 * [OUTPUT]
 * gapEvents: CAPABILITY_GAP / SKILL_GAP SSE handler with toast enable-and-resend;
 * surface_unavailable shows info-only toast (no enable/resend);
 * web_search not_configured|unreachable → SSOT config-gap toast (agent mode relies on SSE only).
 *
 * [POS]
 * SSE handlers for capability/skill entitlement gaps from stream preflight and discover_capability_tool.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import {
  BUILTIN_TOOL_LABELS,
  isBuiltinToolId,
  type BuiltinToolId,
} from '@/store/chat/types/builtinTools';
import { toast } from '@/lib/utils/toast';
import {
  flushPendingGapRetry,
  resolveLastPlainUserMessage,
} from '@/store/chat/pendingGapRetry';
import { renderUiSurfaceUnavailableMessage } from './renderUiSurfaceUnavailableMessage';
import {
  resolveWebSearchConfigGapActionLabel,
  runWebSearchConfigGapAction,
  SEARCH_SETTINGS_PATH,
} from '@/store/config/webSearchConfigGap';

function storePendingGapRetry(
  kind: 'capability' | 'skill',
  text: string,
  id: BuiltinToolId | string,
): void {
  const store = H.useChatStore.getState();
  if (kind === 'capability') {
    store.setPendingGapRetry({ kind: 'capability', text, toolId: id as BuiltinToolId });
    return;
  }
  store.setPendingGapRetry({ kind: 'skill', text, skillId: id });
}

export async function gapEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data } = ctx;
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');

  if (data.type === H.AgentEventType.CAPABILITY_GAP) {
    const payload = data.data as {
      tool_id?: string;
      tool_group?: string;
      reason?: string;
      display_message?: string;
      settings_path?: string;
    } | undefined;
    const toolId = payload?.tool_id;
    if (!toolId || !isBuiltinToolId(toolId)) {
      return null;
    }

    if (payload?.reason === 'not_configured' || payload?.reason === 'unreachable') {
      const message =
        typeof payload.display_message === 'string' && payload.display_message.trim()
          ? payload.display_message.trim()
          : isZh
            ? '网页搜索未配置或不可用，请前往设置。'
            : 'Web search is not configured or unavailable. Open Settings.';
      const settingsPath =
        typeof payload.settings_path === 'string' && payload.settings_path.trim()
          ? payload.settings_path.trim()
          : SEARCH_SETTINGS_PATH;
      const actionLabel = resolveWebSearchConfigGapActionLabel(isZh);

      toast.info(message, {
        duration: 12000,
        action: {
          label: actionLabel,
          onClick: () => {
            void runWebSearchConfigGapAction(settingsPath);
          },
        },
      });
      return done(ctx);
    }

    if (payload?.reason === 'surface_unavailable') {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : null;
      const message =
        typeof payload.display_message === 'string' && payload.display_message.trim()
          ? payload.display_message.trim()
          : renderUiSurfaceUnavailableMessage(lang);
      toast.info(message, { duration: 12000 });
      return done(ctx);
    }

    const store = H.useChatStore.getState();
    const retryText = resolveLastPlainUserMessage(store.messages);
    if (retryText) {
      storePendingGapRetry('capability', retryText, toolId);
    }

    const label = isZh ? BUILTIN_TOOL_LABELS[toolId].zh : BUILTIN_TOOL_LABELS[toolId].en;
    const message = isZh
      ? `完成此任务需要开启「${label}」`
      : `Enable "${label}" to complete this task`;
    const actionLabel = isZh ? '开启并重发' : 'Enable & resend';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: async () => {
          const latestStore = H.useChatStore.getState();
          const prev = latestStore.currentBuiltinTools;
          if (!prev.includes(toolId)) {
            latestStore.setCurrentBuiltinTools([...prev, toolId as BuiltinToolId]);
          }
          const resent = await flushPendingGapRetry();
          if (resent) {
            toast.success(
              isZh ? '已开启并重新发送您的请求' : 'Enabled and resent your request.',
            );
            return;
          }
          if (latestStore.loading) {
            toast.success(
              isZh
                ? '已开启，本轮结束后将自动重发'
                : 'Enabled. Will resend after this turn finishes.',
            );
            return;
          }
          toast.success(
            isZh ? '已开启，请重试刚才的请求' : 'Enabled. Please retry your request.',
          );
        },
      },
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.SKILL_GAP) {
    const payload = data.data as { skill_id?: string } | undefined;
    const skillId = payload?.skill_id;
    if (!skillId) {
      return null;
    }

    const store = H.useChatStore.getState();
    const retryText = resolveLastPlainUserMessage(store.messages);
    if (retryText) {
      storePendingGapRetry('skill', retryText, skillId);
    }

    const message = isZh
      ? `完成此任务需要绑定技能「${skillId}」`
      : `Bind skill "${skillId}" to complete this task`;
    const actionLabel = isZh ? '绑定并重发' : 'Bind & resend';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: async () => {
          const latestStore = H.useChatStore.getState();
          const prev = latestStore.agentConfig?.selectedSkillIds ?? [];
          if (!prev.includes(skillId)) {
            latestStore.updateAgentConfig({ selectedSkillIds: [...prev, skillId] });
          }
          const resent = await flushPendingGapRetry();
          if (resent) {
            toast.success(
              isZh ? '已绑定并重新发送您的请求' : 'Skill bound and resent your request.',
            );
            return;
          }
          if (latestStore.loading) {
            toast.success(
              isZh
                ? '已绑定，本轮结束后将自动重发'
                : 'Skill bound. Will resend after this turn finishes.',
            );
            return;
          }
          toast.success(isZh ? '已绑定，请重试刚才的请求' : 'Skill bound. Please retry your request.');
        },
      },
    });
    return done(ctx);
  }

  return null;
}
