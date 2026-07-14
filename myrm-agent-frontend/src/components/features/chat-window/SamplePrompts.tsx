'use client';

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Search,
  Scale,
  Lightbulb,
  Brain,
  PenTool,
  GitCompare,
  Newspaper,
  Link2,
  Code2,
  HeartPulse,
  BookMarked,
  Container,
  Timer,
  Cpu,
  FileText,
  CalendarDays,
  Zap,
  FileEdit,
  Target,
  ClipboardList,
  Database,
  Megaphone,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import type { ActionMode } from '@/store/chat/types';

const POOL_SIZE = 12;
const DISPLAY_COUNT = 4;

const PROMPT_ICONS: Record<string, LucideIcon> = {
  fast_0: Search,
  fast_1: Scale,
  fast_2: Lightbulb,
  fast_3: Newspaper,
  fast_4: Link2,
  fast_5: Code2,
  fast_6: HeartPulse,
  fast_7: BookMarked,
  fast_8: Container,
  fast_9: Timer,
  fast_10: Cpu,
  fast_11: FileText,
  agent_0: Brain,
  agent_1: PenTool,
  agent_2: GitCompare,
  agent_3: CalendarDays,
  agent_4: Zap,
  agent_5: FileEdit,
  agent_6: Target,
  agent_7: ClipboardList,
  agent_8: Database,
  agent_9: Megaphone,
  agent_10: TrendingUp,
  agent_11: Users,
};

const SUPPORTED_MODES: ActionMode[] = ['fast', 'agent'];

function hashSeed(seed: string): number {
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function stablePick<T>(items: T[], count: number, seed: string): T[] {
  const shuffled = [...items];
  let state = hashSeed(seed);
  for (let i = shuffled.length - 1; i > 0; i--) {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    const j = state % (i + 1);
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled.slice(0, count);
}

const SamplePrompts = React.memo(() => {
  const t = useTranslations('chat');
  const actionMode = useChatStore((state) => state.actionMode);
  const setInputMessage = useChatStore((state) => state.setInputMessage);
  const agentConfig = useChatStore((state) => state.agentConfig);

  const mode = SUPPORTED_MODES.includes(actionMode) ? actionMode : 'agent';

  const prompts = useMemo(() => {
    const pickSeed = `${mode}:${agentConfig?.agentId ?? agentConfig?.presetId ?? 'default'}`;

    // 优先使用智能体自定义提示（如果有）
    if (agentConfig?.suggestionPrompts && agentConfig.suggestionPrompts.length > 0) {
      const agentPrompts = agentConfig.suggestionPrompts.map((text, i) => ({
        key: `agent_custom_${i}`,
        text,
        Icon: PROMPT_ICONS[`agent_${i % POOL_SIZE}`] ?? Brain,
      }));
      return stablePick(agentPrompts, DISPLAY_COUNT, `${pickSeed}:custom`);
    }

    // fallback: 从模式提示池中稳定选取（SSR/CSR 一致，避免 hydration mismatch）
    const pool = Array.from({ length: POOL_SIZE }, (_, i) => {
      const key = `${mode}_${i}`;
      return {
        key,
        text: t(`samplePrompts.${key}`),
        Icon: PROMPT_ICONS[key] ?? Search,
      };
    });
    return stablePick(pool, DISPLAY_COUNT, pickSeed);
  }, [mode, t, agentConfig?.agentId, agentConfig?.presetId, agentConfig?.suggestionPrompts]);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 w-full animate-in fade-in duration-500">
      {prompts.map(({ key, text, Icon }) => (
        <button
          key={key}
          onClick={() => setInputMessage(text)}
          className="group flex items-start gap-3 p-3.5 rounded-xl border border-border/60 bg-secondary/40
                     hover:bg-secondary hover:border-border hover:shadow-sm
                     transition-all duration-200 text-left cursor-pointer"
        >
          <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
          <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors line-clamp-2">
            {text}
          </span>
        </button>
      ))}
    </div>
  );
});

SamplePrompts.displayName = 'SamplePrompts';

export default SamplePrompts;
