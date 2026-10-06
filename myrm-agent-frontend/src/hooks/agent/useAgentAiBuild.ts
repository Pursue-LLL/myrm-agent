import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';

import type { useAgentEditor } from '@/hooks/agent/useAgentEditor';
import { toast } from '@/hooks/shared/useToast';
import { getApiUrl } from '@/lib/api';
import type { BuiltinToolId } from '@/store/chat/types';

type AgentEditor = ReturnType<typeof useAgentEditor>;

/** The part of the editor a generated draft is applied to. */
export type AiBuildTarget = Pick<
  AgentEditor,
  'setName' | 'setDescription' | 'enabledSkills' | 'enabledMcps' | 'handleConfigChange'
>;

interface AiBuildDraft {
  name?: string;
  description?: string;
  system_prompt?: string;
  skill_ids?: unknown;
  mcp_ids?: unknown;
  builtin_tools?: unknown;
}

// Tools the builder may switch on; anything else the model invents is dropped.
const BUILDER_TOOL_IDS = new Set(['browser', 'shell_exec', 'code_exec', 'file_ops', 'search', 'image_gen']);

/** Concatenates the `content` events of the builder's SSE stream. */
async function readBuilderStream(response: Response): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }
  const decoder = new TextDecoder();
  let buffer = '';
  let text = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) {
        continue;
      }
      try {
        const event: { type?: string; data?: unknown } = JSON.parse(line.slice(6));
        if (event.type === 'content' && typeof event.data === 'string') {
          text += event.data;
        }
      } catch {
        /* skip malformed SSE chunks */
      }
    }
  }
  return text;
}

/** The model may wrap its JSON in a code fence or prose; only the outermost object is kept. */
function parseDraft(text: string): AiBuildDraft {
  let cleaned = text.trim();
  cleaned = cleaned.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?\s*```\s*$/i, '');
  const jsonStart = cleaned.indexOf('{');
  const jsonEnd = cleaned.lastIndexOf('}');
  if (jsonStart !== -1 && jsonEnd > jsonStart) {
    cleaned = cleaned.slice(jsonStart, jsonEnd + 1);
  }
  return JSON.parse(cleaned) as AiBuildDraft;
}

/** "Describe the agent you want" flow of the create page: streams a draft and applies the parts that resolve. */
export function useAgentAiBuild(editor: AiBuildTarget) {
  const t = useTranslations();
  const { setName, setDescription, enabledSkills, enabledMcps, handleConfigChange } = editor;
  const [aiIntent, setAiIntent] = useState('');
  const [aiGenerating, setAiGenerating] = useState(false);

  const handleAiBuild = useCallback(
    async (intent: string) => {
      if (!intent.trim() || aiGenerating) {
        return;
      }
      setAiGenerating(true);
      try {
        const response = await fetch(getApiUrl('/user-agents/ai-build'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent, locale: navigator.language || 'en-US' }),
        });
        if (!response.ok) {
          const err = await response.json().catch(() => null);
          throw new Error(err?.detail || `HTTP ${response.status}`);
        }
        const draft = parseDraft(await readBuilderStream(response));

        if (draft.name) {
          setName(draft.name);
        }
        if (draft.description) {
          setDescription(draft.description);
        }

        const validSkillIds = new Set(enabledSkills.map((s) => s.id));
        const validMcpNames = new Set(enabledMcps.map((m) => m.name));

        handleConfigChange({
          ...(draft.system_prompt ? { systemPrompt: draft.system_prompt } : {}),
          ...(Array.isArray(draft.skill_ids)
            ? { selectedSkillIds: (draft.skill_ids as string[]).filter((id) => validSkillIds.has(id)) }
            : {}),
          ...(Array.isArray(draft.mcp_ids)
            ? { selectedMcpNames: (draft.mcp_ids as string[]).filter((id) => validMcpNames.has(id)) }
            : {}),
          ...(Array.isArray(draft.builtin_tools)
            ? {
                enabledBuiltinTools: (draft.builtin_tools as string[]).filter((id) =>
                  BUILDER_TOOL_IDS.has(id),
                ) as BuiltinToolId[],
              }
            : {}),
        });
        setAiIntent('');
        toast({ title: t('agent.aiBuilder.apply') });
      } catch (e) {
        console.error('AI Build failed:', e);
        toast({
          title: t('agent.aiBuilder.error'),
          description: e instanceof Error ? e.message : undefined,
          variant: 'destructive',
        });
      } finally {
        setAiGenerating(false);
      }
    },
    [aiGenerating, enabledMcps, enabledSkills, handleConfigChange, setDescription, setName, t],
  );

  return { aiIntent, setAiIntent, aiGenerating, handleAiBuild };
}
