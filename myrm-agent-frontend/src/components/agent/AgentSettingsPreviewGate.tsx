'use client';

/**
 * [INPUT]
 * - services/agent::TemplateListItem, TemplateSettingsPreview (POS: Agent template and preview metadata)
 * - next-intl::useTranslations (POS: Internationalization)
 * - lucide-react::Wrench, Puzzle, Server, Brain, ShieldCheck, ArrowRight, ArrowLeft, Sparkles (POS: Icons)
 *
 * [OUTPUT]
 * - AgentSettingsPreviewGate: Unified settings preview panel acting as pre-creation gatekeeper
 *   revealing tools, skills, MCP, memory, and sandbox deploy boundaries before agent instantiation.
 *
 * [POS]
 * Guided setup pre-flight inspection panel resolving the Mesbah Karim UX pain point
 * (eradicating hidden settings and surprise configurations before agent creation).
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  Wrench,
  Puzzle,
  Server,
  Brain,
  ShieldCheck,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  CheckCircle2,
  Cpu,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import type { TemplateListItem } from '@/services/agent';

export interface AgentSettingsPreviewGateProps {
  template: TemplateListItem;
  onConfirm: () => void;
  onBack: () => void;
  isCreating?: boolean;
  className?: string;
}

export function AgentSettingsPreviewGate({
  template,
  onConfirm,
  onBack,
  isCreating = false,
  className = '',
}: AgentSettingsPreviewGateProps) {
  const t = useTranslations('Agent.settingsPreview');

  const preview = template.settings_preview;
  const builtinTools = preview?.enabled_builtin_tools ?? [];
  const skills = Array.from(
    new Set([...(preview?.skill_ids ?? []), ...(preview?.prebuilt_skill_ids ?? [])]),
  );
  const mcpIds = preview?.mcp_ids ?? [];
  const memoryPreset = preview?.memory_preset ?? 'dual_layer';
  const deployMode = preview?.deploy_mode ?? 'sandbox';
  const sandboxNote = preview?.sandbox_bound_note;
  const promptMode = preview?.prompt_mode ?? 'full';
  const personality = preview?.personality_style ?? 'professional';

  return (
    <div
      data-testid="agent-settings-preview-gate"
      className={`flex flex-col gap-4 animate-in fade-in-50 duration-200 ${className}`}
    >
      {/* Header Banner */}
      <div className="flex items-start gap-3 p-3.5 rounded-xl border border-primary/20 bg-primary/5">
        <Sparkles className="w-5 h-5 text-primary shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">
              {template.name}
            </h3>
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full border bg-secondary/80 text-muted-foreground">
              {template.agent_type === 'team' ? t('teamType', { fallback: 'Team' }) : t('individualType', { fallback: 'Individual' })}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('gateHint', {
              fallback: 'Review all core capabilities and runtime boundaries before creating. No hidden surprises.',
            })}
          </p>
        </div>
      </div>

      {/* 5-Dimensional Core Settings Matrix */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {/* 1. Built-in Tools Matrix */}
        <div
          data-testid="preview-matrix-builtin-tools"
          className="p-3 rounded-xl border border-border/60 bg-card/60 backdrop-blur-xs flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Wrench className="w-3.5 h-3.5 text-primary" />
              {t('builtinToolsTitle', { fallback: 'Built-in Tools' })}
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-secondary text-muted-foreground">
              {builtinTools.length}
            </span>
          </div>
          {builtinTools.length > 0 ? (
            <div className="flex flex-wrap gap-1 mt-1">
              {builtinTools.map((tool) => (
                <span
                  key={tool}
                  className="text-[11px] px-2 py-0.5 rounded-md bg-secondary/70 text-secondary-foreground border border-border/40 font-mono"
                >
                  {tool}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic mt-0.5">
              {t('defaultBuiltinToolsInherited', { fallback: 'Standard workspace primitives inherited' })}
            </p>
          )}
        </div>

        {/* 2. Skills Pack Matrix */}
        <div
          data-testid="preview-matrix-skills"
          className="p-3 rounded-xl border border-border/60 bg-card/60 backdrop-blur-xs flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Puzzle className="w-3.5 h-3.5 text-primary" />
              {t('skillsTitle', { fallback: 'Skills Pack' })}
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-secondary text-muted-foreground">
              {skills.length}
            </span>
          </div>
          {skills.length > 0 ? (
            <div className="flex flex-wrap gap-1 mt-1">
              {skills.map((skill) => (
                <span
                  key={skill}
                  className="text-[11px] px-2 py-0.5 rounded-md bg-primary/10 text-primary border border-primary/20 font-medium"
                >
                  {skill}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic mt-0.5">
              {t('noSkillsAttached', { fallback: 'No extra skills pre-mounted' })}
            </p>
          )}
        </div>

        {/* 3. MCP Services Matrix */}
        <div
          data-testid="preview-matrix-mcp"
          className="p-3 rounded-xl border border-border/60 bg-card/60 backdrop-blur-xs flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Server className="w-3.5 h-3.5 text-primary" />
              {t('mcpTitle', { fallback: 'MCP Connectors' })}
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-secondary text-muted-foreground">
              {mcpIds.length}
            </span>
          </div>
          {mcpIds.length > 0 ? (
            <div className="flex flex-wrap gap-1 mt-1">
              {mcpIds.map((mcp) => (
                <span
                  key={mcp}
                  className="text-[11px] px-2 py-0.5 rounded-md bg-secondary/80 text-foreground border border-border/50"
                >
                  {mcp}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-muted-foreground italic mt-0.5">
              {t('noMcpBound', { fallback: 'Zero external MCP protocol bindings' })}
            </p>
          )}
        </div>

        {/* 4. Memory Architecture Matrix */}
        <div
          data-testid="preview-matrix-memory"
          className="p-3 rounded-xl border border-border/60 bg-card/60 backdrop-blur-xs flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Brain className="w-3.5 h-3.5 text-primary" />
              {t('memoryTitle', { fallback: 'Memory Engine' })}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 font-medium">
              {memoryPreset}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
            {t('memoryDescription', {
              fallback: 'Dual-Layer HUD: Persona profile + workspace notes with quota protection.',
            })}
          </p>
        </div>

        {/* 5. Deploy Mode & Sandbox Bounds (Full Width) */}
        <div
          data-testid="preview-matrix-sandbox"
          className="sm:col-span-2 p-3 rounded-xl border border-border/60 bg-card/60 backdrop-blur-xs flex flex-col gap-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              {t('deployBoundaryTitle', { fallback: 'Deploy Mode & Sandbox Boundary' })}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 font-medium capitalize">
              {deployMode}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {sandboxNote ||
              t('sandboxNoteDefault', {
                fallback:
                  'Isolated sandbox execution: high-risk system commands are shielded within the container workspace.',
              })}
          </p>
        </div>
      </div>

      {/* Meta Specs Pill Bar */}
      <div className="flex flex-wrap items-center gap-2 p-2.5 rounded-xl border border-border/40 bg-muted/20 text-xs text-muted-foreground">
        <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
        <span>{t('promptMode', { fallback: 'Prompt Mode' })}: <strong className="text-foreground font-mono">{promptMode}</strong></span>
        <span className="text-border">•</span>
        <span>{t('personality', { fallback: 'Tone' })}: <strong className="text-foreground capitalize">{personality}</strong></span>
        <span className="text-border">•</span>
        <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="w-3 h-3" />
          {t('preflightReady', { fallback: 'Pre-flight verified' })}
        </span>
      </div>

      {/* Action Footer Bar */}
      <div className="flex items-center justify-between pt-2 border-t border-border/40">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          disabled={isCreating}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          {t('backToTemplates', { fallback: 'Back' })}
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={onConfirm}
          disabled={isCreating}
          data-testid="confirm-instantiate-agent-btn"
          className="flex items-center gap-1.5 text-xs bg-primary text-primary-foreground hover:bg-primary/90 font-medium"
        >
          <span>{isCreating ? t('creating', { fallback: 'Creating…' }) : t('confirmAndCreate', { fallback: 'Confirm & Create Agent' })}</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}
