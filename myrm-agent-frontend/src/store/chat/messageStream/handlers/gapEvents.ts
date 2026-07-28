/**
 * [INPUT]
 * ../streamContext::StreamCtx (POS: per-SSE-event reducer context)
 * ./handlerDeps::useChatStore (POS: chat session store access)
 *
 * [OUTPUT]
 * gapEvents: CAPABILITY_GAP SSE handler for factual gaps only (migration, web_search config,
 * render_ui surface_unavailable). Substring entitlement enable-and-resend toasts removed.
 *
 * [POS]
 * SSE handlers for non-ambiguous capability gaps from stream preflight.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import { isBuiltinToolId } from '@/store/chat/types/builtinTools';
import { toast } from '@/lib/utils/toast';
import { renderUiSurfaceUnavailableMessage } from './renderUiSurfaceUnavailableMessage';
import {
  resolveWebSearchConfigGapActionLabel,
  runWebSearchConfigGapAction,
  SEARCH_SETTINGS_PATH,
} from '@/store/config/webSearchConfigGap';

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

    if (payload?.reason === 'migration_readiness_critical' || payload?.reason === 'migration_readiness_warning') {
      const message =
        typeof payload.display_message === 'string' && payload.display_message.trim()
          ? payload.display_message.trim()
          : isZh
            ? payload?.reason === 'migration_readiness_warning'
              ? '迁移助手可以聊天，但仍有待完成项，建议先查看设置。'
              : '迁移助手尚未就绪，请先在设置中配置模型提供商。'
            : payload?.reason === 'migration_readiness_warning'
              ? 'This migrated assistant can chat, but migration follow-ups remain in Settings.'
              : 'This migrated assistant is not ready to chat. Configure model providers in Settings.';
      const settingsPath =
        typeof payload.settings_path === 'string' && payload.settings_path.trim()
          ? payload.settings_path.trim()
          : '/settings/models';
      toast.info(message, {
        duration: 12000,
        action: {
          label: isZh ? '前往设置' : 'Go to Settings',
          onClick: () => {
            if (typeof window !== 'undefined') {
              window.location.assign(settingsPath);
            }
          },
        },
      });
      return done(ctx);
    }

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
      const docLang = typeof document !== 'undefined' ? document.documentElement.lang : null;
      const message =
        typeof payload.display_message === 'string' && payload.display_message.trim()
          ? payload.display_message.trim()
          : renderUiSurfaceUnavailableMessage(docLang);
      toast.info(message, { duration: 12000 });
      return done(ctx);
    }

    return null;
  }

  if (data.type === H.AgentEventType.SKILL_GAP) {
    return null;
  }

  return null;
}
