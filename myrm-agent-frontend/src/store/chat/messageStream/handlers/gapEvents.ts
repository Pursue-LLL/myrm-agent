/**
 * [POS]
 * SSE handlers for capability/skill entitlement gaps surfaced by discover_capability_tool.
 */

import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import * as H from './handlerDeps';
import {
  BUILTIN_TOOL_IDS,
  type BuiltinToolId,
} from '@/store/chat/types/builtinTools';
import { toast } from '@/lib/utils/toast';

const BUILTIN_TOOL_ID_SET = new Set<string>(BUILTIN_TOOL_IDS);

function isBuiltinToolId(value: string): value is BuiltinToolId {
  return BUILTIN_TOOL_ID_SET.has(value);
}

const TOOL_LABELS: Record<BuiltinToolId, { en: string; zh: string }> = {
  web_search: { en: 'Web Search', zh: '网页搜索' },
  memory: { en: 'Memory', zh: '记忆' },
  wiki: { en: 'Wiki', zh: 'Wiki' },
  browser: { en: 'Browser', zh: '浏览器' },
  computer_use: { en: 'Computer Use', zh: '桌面控制' },
  image_generation: { en: 'Image Generation', zh: '图片生成' },
  video_generation: { en: 'Video Generation', zh: '视频生成' },
  tts: { en: 'Text to Speech', zh: '语音合成' },
  kanban: { en: 'Kanban', zh: '看板' },
  cron: { en: 'Scheduled Tasks', zh: '定时任务' },
  answer_tool: { en: 'Answer Tool', zh: '答案工具' },
  render_ui: { en: 'Render UI', zh: 'UI 渲染' },
  planning: { en: 'Planning', zh: '任务规划' },
};

export async function gapEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data } = ctx;
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  const isZh = lang?.startsWith('zh');

  if (data.type === H.AgentEventType.CAPABILITY_GAP) {
    const payload = data.data as { tool_id?: string; tool_group?: string } | undefined;
    const toolId = payload?.tool_id;
    if (!toolId || !isBuiltinToolId(toolId)) {
      return null;
    }

    const label = isZh ? TOOL_LABELS[toolId].zh : TOOL_LABELS[toolId].en;
    const message = isZh
      ? `完成此任务需要开启「${label}」`
      : `Enable "${label}" to complete this task`;
    const actionLabel = isZh ? '一键开启' : 'Enable now';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: () => {
          const store = H.useChatStore.getState();
          const prev = store.currentBuiltinTools;
          if (!prev.includes(toolId)) {
            store.setCurrentBuiltinTools([...prev, toolId]);
            toast.success(isZh ? '已开启，请重试刚才的请求' : 'Enabled. Please retry your request.');
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
      ? `完成此任务需要绑定技能「${skillId}」`
      : `Bind skill "${skillId}" to complete this task`;
    const actionLabel = isZh ? '一键绑定' : 'Bind now';

    toast.info(message, {
      duration: 12000,
      action: {
        label: actionLabel,
        onClick: () => {
          const store = H.useChatStore.getState();
          const prev = store.agentConfig?.selectedSkillIds ?? [];
          if (!prev.includes(skillId)) {
            store.updateAgentConfig({ selectedSkillIds: [...prev, skillId] });
            toast.success(isZh ? '已绑定，请重试刚才的请求' : 'Skill bound. Please retry your request.');
          }
        },
      },
    });
    return done(ctx);
  }

  return null;
}
