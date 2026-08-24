'use client';

import { useMemo, useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import {
  IconZap,
  IconShield,
  IconBrain,
  IconCheck,
  IconEye,
  IconCode,
  IconChevronDown,
} from '@/components/features/icons/PremiumIcons';
import { Sparkles, Layers, Cpu } from 'lucide-react';
import { fetchModelCapabilitiesBatch, type ModelCapabilities } from '@/services/llm-config';
import { formatTokens } from '@/lib/utils/modelFormatUtils';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';

interface ModelSwapContinuityCardProps {
  editor: AgentCapabilitiesTabProps['editor'];
  effectiveModelSlug: string;
}

/**
 * ModelSwapContinuityCard:
 * 资产连续性保障与底层模型能力适配诊断卡片。
 * 直观呈现：
 * 1. 资产 100% 连续保留凭证（Skills, MCP, Memory, Workspace Rules, Subagents 全部安全继承）；
 * 2. 模型专属 Execution Discipline 与 Prompt 偏好建议；
 * 3. 多模态 Vision 兼容性与 Fallback 路由接管状态；
 * 4. 上下文窗口容量感知。
 */
export function ModelSwapContinuityCard({ editor, effectiveModelSlug }: ModelSwapContinuityCardProps) {
  const t = useTranslations('agent.continuity');
  const [capabilities, setCapabilities] = useState<ModelCapabilities | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!effectiveModelSlug) {
      setCapabilities(null);
      return;
    }
    let isMounted = true;
    fetchModelCapabilitiesBatch([effectiveModelSlug])
      .then((res) => {
        if (isMounted && res[effectiveModelSlug]) {
          setCapabilities(res[effectiveModelSlug]);
        }
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, [effectiveModelSlug]);

  const skillCount = editor.selectedSkillDetails?.length ?? 0;
  const mcpCount = editor.selectedMcpDetails?.length ?? 0;
  const subagentCount = editor.selectedSubagentIds?.length ?? 0;
  const openapiCount = editor.openapiServices?.length ?? 0;
  const hasWorkspaceRules = !!editor.workspacePolicy;

  const modelFamilyDiscipline = useMemo(() => {
    const slug = effectiveModelSlug.toLowerCase();
    if (slug.includes('claude') || slug.includes('anthropic')) {
      return {
        family: 'Claude',
        discipline: t('disciplineClaude'),
        promptMode: 'Full',
      };
    }
    if (slug.includes('deepseek')) {
      return {
        family: 'DeepSeek',
        discipline: t('disciplineDeepSeek'),
        promptMode: 'Lean / Full',
      };
    }
    if (
      slug.includes('gpt') ||
      slug.includes('codex') ||
      slug.includes('openai') ||
      slug.includes('o1') ||
      slug.includes('o3')
    ) {
      return {
        family: 'OpenAI GPT/Codex',
        discipline: t('disciplineGpt'),
        promptMode: 'Full',
      };
    }
    if (slug.includes('gemini') || slug.includes('gemma')) {
      return {
        family: 'Gemini',
        discipline: t('disciplineGemini'),
        promptMode: 'Lean',
      };
    }
    if (slug.includes('qwen') || slug.includes('glm')) {
      return {
        family: 'Qwen/GLM',
        discipline: t('disciplineQwen'),
        promptMode: 'Lean / Full',
      };
    }
    return {
      family: 'Universal',
      discipline: t('disciplineUniversal'),
      promptMode: 'Full',
    };
  }, [effectiveModelSlug, t]);

  return (
    <div className="mt-3 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs text-foreground/90 transition-all">
      {/* Header Summary */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-medium text-primary">
          <Sparkles className="h-4 w-4 shrink-0" />
          <span>{t('title')}</span>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
        >
          <span>{expanded ? t('collapse') : t('expandDetails')}</span>
          <IconChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
        </button>
      </div>

      {/* Asset Continuity Chips */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <div className="flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          <IconCheck className="h-3 w-3 shrink-0" />
          <span>{t('assetSkills', { count: skillCount })}</span>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          <IconCheck className="h-3 w-3 shrink-0" />
          <span>{t('assetMcp', { count: mcpCount })}</span>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          <IconCheck className="h-3 w-3 shrink-0" />
          <span>{t('assetMemory')}</span>
        </div>
        <div className="flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
          <IconCheck className="h-3 w-3 shrink-0" />
          <span>{t('assetWorkspace')}</span>
        </div>
        {subagentCount > 0 && (
          <div className="flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-400">
            <IconCheck className="h-3 w-3 shrink-0" />
            <span>{t('assetSubagents', { count: subagentCount })}</span>
          </div>
        )}
      </div>

      {/* Expanded Details Panel */}
      {expanded && (
        <div className="mt-3 space-y-2 border-t border-border/60 pt-2.5">
          {/* Model Family Discipline */}
          <div className="flex items-start gap-2 rounded-md bg-background/60 p-2 border border-border/40">
            <Cpu className="h-4 w-4 shrink-0 text-primary mt-0.5" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 font-medium text-foreground text-[11px]">
                <span>{t('disciplineTitle', { family: modelFamilyDiscipline.family })}</span>
                <span className="rounded bg-primary/10 px-1.5 py-0.2 text-[10px] text-primary">
                  {t('recommendedPromptMode', { mode: modelFamilyDiscipline.promptMode })}
                </span>
              </div>
              <p className="mt-0.5 text-[11px] text-muted-foreground leading-relaxed">
                {modelFamilyDiscipline.discipline}
              </p>
            </div>
          </div>

          {/* Capabilities & Vision Safeguard */}
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-md bg-background/60 p-2 border border-border/40 space-y-1">
              <div className="text-muted-foreground flex items-center gap-1">
                <Layers className="h-3.5 w-3.5" />
                <span>{t('contextWindow')}</span>
              </div>
              <div className="font-semibold text-foreground">
                {capabilities?.max_input_tokens ? formatTokens(capabilities.max_input_tokens) : t('unlimitedOrAuto')}
              </div>
            </div>

            <div className="rounded-md bg-background/60 p-2 border border-border/40 space-y-1">
              <div className="text-muted-foreground flex items-center gap-1">
                <IconEye className="h-3.5 w-3.5" />
                <span>{t('visionSupport')}</span>
              </div>
              <div className="font-semibold text-foreground flex items-center gap-1">
                {capabilities?.supports_vision ? (
                  <span className="text-emerald-600 dark:text-emerald-400">{t('visionNative')}</span>
                ) : (
                  <span className="text-amber-600 dark:text-amber-400">{t('visionFallbackActive')}</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
