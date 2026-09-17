/**
 * Tool Guidance Evolution & Governance Panel.
 *
 * Visualizes distilled behavioral rules and avoidance guidelines per tool.
 * Enables users to inspect golden guidelines, toggle pinned rules, and prune obsolete experiences.
 */

'use client';

import React, { useCallback, useEffect, useState, useTransition } from 'react';

import {
  Wrench,
  Pin,
  PinOff,
  Trash2,
  ShieldCheck,
  Sparkles,
  Terminal,
  Layers,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import {
  getToolGuidance,
  pinToolGuidance,
  deleteToolGuidance,
  type ToolGuidanceGroupDTO,
  type ToolGuidanceItemDTO,
} from '@/services/memory/toolGuidance';

interface ToolGuidancePanelProps {
  className?: string;
}

export const ToolGuidancePanel: React.FC<ToolGuidancePanelProps> = ({ className = '' }) => {
  const [tools, setTools] = useState<ToolGuidanceGroupDTO[]>([]);
  const [totalTools, setTotalTools] = useState(0);
  const [totalRules, setTotalRules] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const loadData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await getToolGuidance();
      setTools(res.tools);
      setTotalTools(res.total_tools);
      setTotalRules(res.total_rules);
      if (res.tools.length > 0 && !selectedTool) {
        setSelectedTool(res.tools[0].tool_name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tool guidance');
    } finally {
      setIsLoading(false);
    }
  }, [selectedTool]);

  useEffect(() => {
    void loadData();
  }, [loadData]);


  const handleTogglePin = (ruleId: string, currentPinned: boolean) => {
    startTransition(async () => {
      try {
        await pinToolGuidance(ruleId, !currentPinned);
        await loadData();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to toggle pin status');
      }
    });
  };

  const handleDelete = (ruleId: string) => {
    startTransition(async () => {
      try {
        await deleteToolGuidance(ruleId);
        await loadData();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete rule');
      }
    });
  };

  const activeGroup = tools.find((t) => t.tool_name === selectedTool) ?? tools[0];

  return (
    <div className={`space-y-4 rounded-xl border border-border bg-card/60 p-4 sm:p-6 backdrop-blur-sm ${className}`}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Wrench className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
              工具自适应规约与经验沉淀
              <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                ReMe 引擎
              </span>
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              自动捕获执行异常与自愈反馈，收敛为确定性 Golden Guidelines 并动态挂载
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <div className="flex items-center gap-3 text-xs text-muted-foreground mr-2">
            <span>活跃工具: <strong className="text-foreground">{totalTools}</strong></span>
            <span>沉淀经验: <strong className="text-foreground">{totalRules}</strong></span>
          </div>
          <button
            type="button"
            onClick={() => void loadData()}
            disabled={isLoading || isPending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading || isPending ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Layout: Tabs + Content */}
      {tools.length === 0 && !isLoading ? (
        <div className="py-12 text-center text-muted-foreground space-y-2">
          <ShieldCheck className="mx-auto h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm font-medium">暂无工具自愈规约记录</p>
          <p className="text-xs text-muted-foreground">当模型调用工具遭遇环境异常并自愈后，将自动在此沉淀黄金指南</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Tool Navigation Sidebar */}
          <div className="md:col-span-1 space-y-1 overflow-x-auto pb-2 md:pb-0 flex md:flex-col gap-1">
            {tools.map((t) => {
              const isSelected = (selectedTool ?? tools[0]?.tool_name) === t.tool_name;
              return (
                <button
                  key={t.tool_name}
                  type="button"
                  onClick={() => setSelectedTool(t.tool_name)}
                  className={`flex items-center justify-between w-full rounded-lg px-3 py-2 text-left text-xs font-medium transition-all ${
                    isSelected
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                >
                  <span className="truncate max-w-[140px] font-mono">{t.tool_name}</span>
                  <div className="flex items-center gap-1">
                    {t.has_pinned && <Pin className="h-3 w-3 shrink-0" />}
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                      isSelected ? 'bg-primary-foreground/20 text-primary-foreground' : 'bg-background/80 text-foreground'
                    }`}>
                      {t.items.length}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Active Tool Details */}
          <div className="md:col-span-3 space-y-4">
            {activeGroup && (
              <>
                {/* Active Golden Guidelines Preview */}
                <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-medium text-primary">
                      <Sparkles className="h-3.5 w-3.5" />
                      <span>已收敛的黄金指南 (JIT Prompt 注入上限 3 条)</span>
                    </div>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      Cache-Stable 字母序排序
                    </span>
                  </div>
                  {activeGroup.guidelines.length > 0 ? (
                    <ul className="space-y-1.5">
                      {activeGroup.guidelines.map((g, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-xs text-foreground bg-background/60 rounded px-2.5 py-1.5 border border-border/50">
                          <span className="font-mono text-primary text-[10px] shrink-0 mt-0.5">#{idx + 1}</span>
                          <span className="font-medium">{g}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground italic">未达到收敛阈值，暂未生成黄金指南</p>
                  )}
                </div>

                {/* Granular Rules Table */}
                <div className="space-y-2">
                  <div className="text-xs font-medium text-foreground flex items-center justify-between">
                    <span>沉淀的规则明细</span>
                    <span className="text-[10px] text-muted-foreground">共 {activeGroup.items.length} 条记录</span>
                  </div>

                  <div className="space-y-2">
                    {activeGroup.items.map((item) => (
                      <RuleItemCard
                        key={item.id}
                        item={item}
                        onTogglePin={handleTogglePin}
                        onDelete={handleDelete}
                        disabled={isPending}
                      />
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

interface RuleItemCardProps {
  item: ToolGuidanceItemDTO;
  onTogglePin: (id: string, isPinned: boolean) => void;
  onDelete: (id: string) => void;
  disabled: boolean;
}

const RuleItemCard: React.FC<RuleItemCardProps> = ({ item, onTogglePin, onDelete, disabled }) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-lg border border-border bg-background/50 p-3 hover:border-border/80 transition-colors">
      <div className="space-y-1 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          {item.is_pinned && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 px-1.5 py-0.5 text-[10px] font-medium border border-amber-500/20">
              <Pin className="h-2.5 w-2.5" /> 已置顶
            </span>
          )}
          {item.env_fingerprint && (
            <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground font-mono">
              <Terminal className="h-2.5 w-2.5" /> {item.env_fingerprint}
            </span>
          )}
          <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground font-mono">
            <Layers className="h-2.5 w-2.5" /> 触发: {item.trigger_pattern}
          </span>
        </div>
        <p className="text-xs text-foreground font-medium pt-0.5">{item.rule_text}</p>
      </div>

      <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
        <button
          type="button"
          onClick={() => onTogglePin(item.id, item.is_pinned)}
          disabled={disabled}
          title={item.is_pinned ? '取消置顶' : '置顶为黄金规则'}
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium border transition-colors ${
            item.is_pinned
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20'
              : 'border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          {item.is_pinned ? <PinOff className="h-3 w-3" /> : <Pin className="h-3 w-3" />}
          <span>{item.is_pinned ? '取消置顶' : '置顶'}</span>
        </button>

        <button
          type="button"
          onClick={() => onDelete(item.id)}
          disabled={disabled}
          title="删除此规则"
          className="inline-flex items-center justify-center rounded-md border border-destructive/20 bg-destructive/5 p-1 text-destructive hover:bg-destructive/10 transition-colors"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
};
