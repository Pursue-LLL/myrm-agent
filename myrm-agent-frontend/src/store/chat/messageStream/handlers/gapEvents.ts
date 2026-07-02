/**
 * [POS]
 * SSE handlers for capability/skill entitlement gaps surfaced by discover_capability_tool.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import type { BuiltinToolId } from '@/store/chat/types/builtinTools';
import { toast } from '@/lib/utils/toast';

function isBuiltinToolId(value: string): value is BuiltinToolId {
  return (
    value === 'web_search' ||
    value === 'memory' ||
    value === 'file_ops' ||
    value === 'code_execute' ||
    value === 'wiki' ||
    value === 'browser' ||
    value === 'computer_use' ||
    value === 'image_generation' ||
    value === 'video_generation' ||
    value === 'tts' ||
    value === 'kanban' ||
    value === 'canvas' ||
    value === 'answer_tool' ||
    value === 'render_ui' ||
    value === 'planning'
  );
}

export async function gapEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');

  if (data.type === H.AgentEventType.CAPABILITY_GAP) {
    const payload = data.data as { tool_id?: string; tool_group?: string } | undefined;
    const toolId = payload?.tool_id;
    if (!toolId || !isBuiltinToolId(toolId)) {
      return null;
    }

    const label = toolId;
    const message = isZh
      ? `完成此任务需要开启内置工具「${label}」`
      : `This task requires enabling builtin tool "${label}"`;
    const actionLabel = isZh ? '一键开启' : 'Enable';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: () => {
          const prev = H.default.useChatStore.getState().currentBuiltinTools;
          if (!prev.includes(toolId)) {
            actions.setCurrentBuiltinTools([...prev, toolId]);
          }
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

    const message = isZh
      ? `此 Agent 未绑定技能「${skillId}」，请在 Agent 设置中勾选后重试`
      : `Skill "${skillId}" is not bound to this Agent. Enable it in Agent settings and retry.`;

    toast.info(message, { duration: 12000 });
    return done(ctx);
  }

  return null;
}
