'use client';

import React, { useState } from 'react';
import {
  Users,
  Sparkles,
  Cpu,
  Coins,
  ShieldCheck,
  ChevronRight,
  ChevronDown,
  X,
  FileCode,
  Wand2,
  CheckCircle2,
} from 'lucide-react';

export type SquadRoleTierType = 'orchestrator' | 'coder' | 'reviewer' | 'researcher' | 'specialist';

export interface StopConditionData {
  max_turns: number;
  max_tool_calls: number;
  allow_failure?: boolean;
}

export interface MemberBlueprintData {
  role_key: string;
  display_name: string;
  handle: string;
  role_tier: SquadRoleTierType;
  role_description: string;
  soul_system_prompt: string;
  required_tools?: string[];
  required_skills?: string[];
  budget_tokens: number;
  max_cost_usd: number;
  stop_condition: StopConditionData;
  suggested_model_tier?: string;
}

export interface SquadBlueprintData {
  squad_id: string;
  goal_description: string;
  members: MemberBlueprintData[];
  total_budget_tokens: number;
  total_max_cost_usd: number;
  max_descendants_per_run: number;
}

export interface ModelChoicePayload {
  role_key: string;
  selected_model_id: string;
  custom_instructions?: string;
}

export interface MaterializedMemberData {
  role_key: string;
  bot_id: string;
  handle: string;
  display_name: string;
  role_tier: SquadRoleTierType;
  selected_model_id: string;
  allocated_budget_tokens: number;
  allocated_max_cost_usd: number;
}

export interface MaterializedSquadData {
  squad_id: string;
  orchestrator_bot_id: string;
  members: MaterializedMemberData[];
  total_budget_tokens: number;
  total_max_cost_usd: number;
  status: string;
}

export interface SquadCompositionWizardProps {
  blueprint?: SquadBlueprintData | null;
  materializedSquad?: MaterializedSquadData | null;
  onComposeBlueprint?: (goal: string, budgetTokens?: number, maxCostUsd?: number) => void;
  onMaterializeSquad?: (squadId: string, choices: ModelChoicePayload[]) => void;
  onClose?: () => void;
  className?: string;
}

const ROLE_TIER_CONFIG: Record<SquadRoleTierType, { label: string; badge: string; defaultModel: string }> = {
  orchestrator: {
    label: '总控编排',
    badge: 'bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border-purple-200 dark:border-purple-800',
    defaultModel: 'gpt-4o',
  },
  coder: {
    label: '核心研发',
    badge: 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    defaultModel: 'claude-3-5-sonnet',
  },
  reviewer: {
    label: '质量卫士',
    badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
    defaultModel: 'gpt-4o-mini',
  },
  researcher: {
    label: '技术侦察',
    badge: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 border-amber-200 dark:border-amber-800',
    defaultModel: 'gemini-1.5-flash',
  },
  specialist: {
    label: '专项特工',
    badge: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
    defaultModel: 'gpt-4o-mini',
  },
};

const AVAILABLE_MODELS = [
  { id: 'gpt-4o', name: 'GPT-4o (强推理)' },
  { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet (架构与代码)' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini (高效均衡)' },
  { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash (超长检索)' },
];

export const SquadCompositionWizard: React.FC<SquadCompositionWizardProps> = ({
  blueprint,
  materializedSquad,
  onComposeBlueprint,
  onMaterializeSquad,
  onClose,
  className = '',
}) => {
  const [goalInput, setGoalInput] = useState<string>('');
  const [step, setStep] = useState<'goal_input' | 'blueprint_review' | 'materialized'>(
    materializedSquad ? 'materialized' : blueprint ? 'blueprint_review' : 'goal_input',
  );
  const [expandedSoulRole, setExpandedSoulRole] = useState<string | null>(null);
  const [modelChoices, setModelChoices] = useState<Record<string, { model: string; instructions: string }>>({});

  const handleComposeSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goalInput.trim() || !onComposeBlueprint) {
      return;
    }
    onComposeBlueprint(goalInput.trim());
    setStep('blueprint_review');
  };

  const handleModelChange = (roleKey: string, modelId: string) => {
    setModelChoices((prev) => ({
      ...prev,
      [roleKey]: {
        model: modelId,
        instructions: prev[roleKey]?.instructions ?? '',
      },
    }));
  };

  const handleInstructionsChange = (roleKey: string, instructions: string) => {
    setModelChoices((prev) => ({
      ...prev,
      [roleKey]: {
        model: prev[roleKey]?.model ?? ROLE_TIER_CONFIG[blueprint?.members.find((m) => m.role_key === roleKey)?.role_tier ?? 'specialist'].defaultModel,
        instructions,
      },
    }));
  };

  const handleMaterialize = () => {
    if (!blueprint || !onMaterializeSquad) {
      return;
    }
    const choices: ModelChoicePayload[] = blueprint.members.map((m) => ({
      role_key: m.role_key,
      selected_model_id: modelChoices[m.role_key]?.model || ROLE_TIER_CONFIG[m.role_tier].defaultModel,
      custom_instructions: modelChoices[m.role_key]?.instructions || '',
    }));
    onMaterializeSquad(blueprint.squad_id, choices);
    setStep('materialized');
  };

  return (
    <section
      aria-label="Orchestrator Squad Composition Wizard"
      className={`flex flex-col border border-border/80 bg-background/95 backdrop-blur-md rounded-xl shadow-xl overflow-hidden transition-all duration-300 ${className}`}
    >
      <div className="flex items-center justify-between px-4 py-3 bg-muted/40 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Wand2 className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-foreground flex items-center gap-2">
              智能战队自动组队向导
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                Model-Deferred 两阶段
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">对标 Hermes El Jefe 编排 · 动态算力预算切分</p>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Wizard"
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="p-4 space-y-4 max-h-[520px] overflow-y-auto">
        {step === 'goal_input' && (
          <form onSubmit={handleComposeSubmit} className="space-y-3">
            <div>
              <label htmlFor="goal-input-area" className="block text-xs font-semibold text-foreground mb-1">
                请输入宏大业务目标 (Goal Intent)
              </label>
              <textarea
                id="goal-input-area"
                rows={3}
                value={goalInput}
                onChange={(e) => setGoalInput(e.target.value)}
                placeholder="例如：重构多智能体信箱路由，编写集成测试并验证安全边界..."
                className="w-full text-xs p-2.5 rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
              />
            </div>
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!goalInput.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5" />
                自动推导蓝图
              </button>
            </div>
          </form>
        )}

        {(step === 'blueprint_review' || (!materializedSquad && blueprint)) && blueprint && (
          <div className="space-y-4">
            <div className="p-3 rounded-lg bg-muted/30 border border-border/80 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-foreground">目标: {blueprint.goal_description}</span>
                <div className="flex items-center gap-3 text-[11px] text-muted-foreground mt-1">
                  <span className="flex items-center gap-1"><Cpu className="w-3 h-3 text-primary" /> {blueprint.total_budget_tokens.toLocaleString()} Tokens</span>
                  <span className="flex items-center gap-1"><Coins className="w-3 h-3 text-amber-500" /> ${blueprint.total_max_cost_usd.toFixed(2)} USD</span>
                  <span className="flex items-center gap-1"><ShieldCheck className="w-3 h-3 text-emerald-500" /> Max {blueprint.max_descendants_per_run} 衍生</span>
                </div>
              </div>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-primary/10 text-primary">
                {blueprint.members.length} 位战队成员
              </span>
            </div>

            <div className="space-y-2">
              <span className="text-xs font-semibold text-foreground">Phase 2: 确认成员角色并选型模型 (Model-Deferred)</span>
              {blueprint.members.map((member) => {
                const tierMeta = ROLE_TIER_CONFIG[member.role_tier];
                const isSoulExpanded = expandedSoulRole === member.role_key;
                const currentModel = modelChoices[member.role_key]?.model || tierMeta.defaultModel;

                return (
                  <div key={member.role_key} className="p-3 rounded-lg border border-border/70 bg-card space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs text-foreground">{member.display_name}</span>
                        <span className="text-[11px] font-mono text-muted-foreground">{member.handle}</span>
                        <span className={`text-[10px] px-2 py-0.2 rounded-full border ${tierMeta.badge}`}>
                          {tierMeta.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <label htmlFor={`select-model-${member.role_key}`} className="sr-only">选择模型</label>
                        <select
                          id={`select-model-${member.role_key}`}
                          value={currentModel}
                          onChange={(e) => handleModelChange(member.role_key, e.target.value)}
                          className="text-xs bg-background border border-border rounded px-2 py-1 focus:ring-1 focus:ring-primary"
                        >
                          {AVAILABLE_MODELS.map((m) => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <p className="text-xs text-muted-foreground">{member.role_description}</p>

                    <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/40">
                      <span>预算: {member.budget_tokens.toLocaleString()} Tokens (${member.max_cost_usd.toFixed(2)})</span>
                      <button
                        type="button"
                        onClick={() => setExpandedSoulRole(isSoulExpanded ? null : member.role_key)}
                        className="text-primary hover:underline flex items-center gap-1"
                      >
                        <FileCode className="w-3 h-3" />
                        {isSoulExpanded ? '收起 SOUL Prompt' : '查看 SOUL Prompt'}
                        {isSoulExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                      </button>
                    </div>

                    {isSoulExpanded && (
                      <pre className="text-[11px] p-2.5 rounded bg-muted font-mono whitespace-pre-wrap text-foreground/90 max-h-36 overflow-y-auto">
                        {member.soul_system_prompt}
                      </pre>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={handleMaterialize}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 shadow transition-colors"
              >
                <CheckCircle2 className="w-4 h-4" />
                物化战队并启动 (Materialize Squad)
              </button>
            </div>
          </div>
        )}

        {step === 'materialized' && materializedSquad && (
          <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-3">
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-bold text-sm">
              <CheckCircle2 className="w-5 h-5" />
              <span>战队物化成功！已就绪自治执行</span>
            </div>
            <p className="text-xs text-muted-foreground">
              战队 ID: <span className="font-mono text-foreground">{materializedSquad.squad_id}</span> · 总控 Bot:{' '}
              <span className="font-mono text-foreground">{materializedSquad.orchestrator_bot_id}</span>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
              {materializedSquad.members.map((m) => (
                <div key={m.role_key} className="p-2.5 rounded-lg border border-border/80 bg-background text-xs">
                  <div className="flex items-center justify-between font-semibold">
                    <span>{m.display_name}</span>
                    <span className="font-mono text-[10px] text-primary">{m.handle}</span>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 flex justify-between">
                    <span>Model: {m.selected_model_id}</span>
                    <span>{m.allocated_budget_tokens.toLocaleString()} Tokens</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

export default SquadCompositionWizard;
