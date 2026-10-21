/**
 * [INPUT]
 * - ./playbookInspectorTypes::PlaybookRule, PlaybookFilter
 * - ./usePlaybookInspectorStore::usePlaybookInspectorStore
 * - ./PlaybookRuleCard::PlaybookRuleCard
 * - lucide-react::ShieldCheck, Search, Plus, Filter, RotateCcw, X, Sparkles
 *
 * [OUTPUT]
 * - PlaybookLifecycleConsole: 判断力规约生命周期全景看板与仲裁工作台组件
 *
 * [POS]
 * 在系统设置、侧边栏或独立抽屉中展示行为规约生命周期状态机、胜率监控与人工复活仲裁。
 */

'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { ShieldCheck, Search, Plus, Filter, RotateCcw, X, Sparkles } from 'lucide-react';
import type { PlaybookFilter } from './playbookInspectorTypes';
import { usePlaybookInspectorStore } from './usePlaybookInspectorStore';
import { PlaybookRuleCard } from './PlaybookRuleCard';

export interface PlaybookLifecycleConsoleProps {
  onClose?: () => void;
  className?: string;
}

export const PlaybookLifecycleConsole: React.FC<PlaybookLifecycleConsoleProps> = ({
  onClose,
  className = '',
}) => {
  const [showAddModal, setShowAddModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newTrigger, setNewTrigger] = useState('');
  const [newDirective, setNewDirective] = useState('');

  const rulesMap = usePlaybookInspectorStore((s) => s.rules);
  const filter = usePlaybookInspectorStore((s) => s.filter);
  const searchQuery = usePlaybookInspectorStore((s) => s.searchQuery);
  const setFilter = usePlaybookInspectorStore((s) => s.setFilter);
  const setSearchQuery = usePlaybookInspectorStore((s) => s.setSearchQuery);
  const reviveRule = usePlaybookInspectorStore((s) => s.reviveRule);
  const togglePinRule = usePlaybookInspectorStore((s) => s.togglePinRule);
  const retireRule = usePlaybookInspectorStore((s) => s.retireRule);
  const updateRule = usePlaybookInspectorStore((s) => s.updateRule);
  const addRule = usePlaybookInspectorStore((s) => s.addRule);
  const reset = usePlaybookInspectorStore((s) => s.reset);

  const rulesList = useMemo(() => Object.values(rulesMap), [rulesMap]);

  const { activeCount, degradedCount, retiredCount, pinnedCount } = useMemo(() => {
    let act = 0;
    let deg = 0;
    let ret = 0;
    let pin = 0;
    for (const r of rulesList) {
      if (r.status === 'active') {
        act += 1;
      } else if (r.status === 'degraded') {
        deg += 1;
      } else if (r.status === 'retired') {
        ret += 1;
      }
      if (r.isPinned) {
        pin += 1;
      }
    }
    return { activeCount: act, degradedCount: deg, retiredCount: ret, pinnedCount: pin };
  }, [rulesList]);

  const filteredRules = useMemo(() => {
    return rulesList.filter((r) => {
      if (filter === 'active' && r.status !== 'active') {
        return false;
      }
      if (filter === 'degraded' && r.status !== 'degraded') {
        return false;
      }
      if (filter === 'retired' && r.status !== 'retired') {
        return false;
      }
      if (filter === 'pinned' && !r.isPinned) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          r.title.toLowerCase().includes(q) ||
          r.triggerCondition.toLowerCase().includes(q) ||
          r.directive.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [rulesList, filter, searchQuery]);

  const handleCreateRule = useCallback(() => {
    if (!newTitle.trim() || !newDirective.trim()) {
      return;
    }
    addRule({
      title: newTitle.trim(),
      triggerCondition: newTrigger.trim() || '任意相关交互',
      directive: newDirective.trim(),
    });
    setNewTitle('');
    setNewTrigger('');
    setNewDirective('');
    setShowAddModal(false);
  }, [newTitle, newTrigger, newDirective, addRule]);

  return (
    <section
      aria-label="判断力规约生命周期治理控制台"
      className={`flex flex-col gap-4 rounded-xl border border-border bg-card/70 p-4 text-xs text-card-foreground shadow-sm backdrop-blur-xs ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-border/70">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="w-5 h-5" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">
                判断力规约生命周期看板
              </h3>
              <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-medium border border-emerald-500/20">
                人类最高仲裁权
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              消除 AI 后台退役规约黑盒，全景追溯胜率曲线并支持一键复活与锁定
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <button
            type="button"
            onClick={() => {
              setShowAddModal(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors shadow-xs"
            aria-label="新建规约"
          >
            <Plus className="w-3.5 h-3.5" aria-hidden="true" />
            <span>新建规约</span>
          </button>
          <button
            type="button"
            onClick={reset}
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors"
            aria-label="恢复默认规约集"
            title="恢复默认规约集"
          >
            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors"
              aria-label="关闭规约治理控制台"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex items-center gap-1 bg-muted/40 p-1 rounded-lg border border-border/50 text-[11px]">
          {(
            [
              { id: 'all', label: `全部 (${rulesList.length})` },
              { id: 'active', label: `生效中 (${activeCount})` },
              { id: 'degraded', label: `降权观察 (${degradedCount})` },
              { id: 'retired', label: `已退役 (${retiredCount})` },
              { id: 'pinned', label: `已锁定 (${pinnedCount})` },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setFilter(tab.id as PlaybookFilter);
              }}
              className={`px-2.5 py-1 rounded transition-colors ${
                filter === tab.id
                  ? 'bg-background text-foreground font-semibold shadow-xs'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="relative min-w-[200px] flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
            placeholder="搜索规约标题、触发词或动作..."
            className="w-full rounded-lg border border-input bg-background/60 pl-8 pr-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
            aria-label="搜索规约"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 min-h-[240px]">
        {filteredRules.length === 0 ? (
          <div className="col-span-full flex flex-col items-center justify-center py-10 text-muted-foreground">
            <Filter className="w-8 h-8 opacity-40 mb-2" aria-hidden="true" />
            <p className="text-xs">未找到匹配的行为规约条目</p>
          </div>
        ) : (
          filteredRules.map((rule) => (
            <PlaybookRuleCard
              key={rule.id}
              rule={rule}
              onRevive={() => {
                reviveRule(rule.id);
              }}
              onTogglePin={() => {
                togglePinRule(rule.id);
              }}
              onRetire={() => {
                retireRule(rule.id);
              }}
              onEdit={(updates) => {
                updateRule(rule.id, updates);
              }}
            />
          ))
        )}
      </div>

      {showAddModal && (
        <dialog
          open
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs border-0 w-full h-full"
        >
          <div
            role="document"
            className="w-full max-w-md rounded-xl border border-border bg-background p-4 shadow-xl text-xs space-y-3"
          >
            <div className="flex items-center justify-between pb-2 border-b border-border/60">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="w-4 h-4 text-primary" aria-hidden="true" />
                <span>新建行为规约</span>
              </h4>
              <button
                type="button"
                onClick={() => {
                  setShowAddModal(false);
                }}
                className="text-muted-foreground hover:text-foreground p-1"
                aria-label="关闭对话框"
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            <div>
              <label
                htmlFor="playbook-rule-title"
                className="block text-[11px] font-medium text-muted-foreground mb-1"
              >
                规约标题 *
              </label>
              <input
                id="playbook-rule-title"
                type="text"
                value={newTitle}
                onChange={(e) => {
                  setNewTitle(e.target.value);
                }}
                placeholder="例如：禁用 any 类型约束"
                className="w-full rounded border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                aria-label="规约标题"
              />
            </div>

            <div>
              <label
                htmlFor="playbook-rule-trigger"
                className="block text-[11px] font-medium text-muted-foreground mb-1"
              >
                触发条件
              </label>
              <input
                id="playbook-rule-trigger"
                type="text"
                value={newTrigger}
                onChange={(e) => {
                  setNewTrigger(e.target.value);
                }}
                placeholder="例如：在生成或重构 TypeScript 模块时"
                className="w-full rounded border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                aria-label="规约触发条件"
              />
            </div>

            <div>
              <label
                htmlFor="playbook-rule-directive"
                className="block text-[11px] font-medium text-muted-foreground mb-1"
              >
                执行动作规约指令 *
              </label>
              <textarea
                id="playbook-rule-directive"
                value={newDirective}
                onChange={(e) => {
                  setNewDirective(e.target.value);
                }}
                rows={3}
                placeholder="详细指示模型在触发时必须遵从的行为规范..."
                className="w-full rounded border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                aria-label="规约指令内容"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-border/40">
              <button
                type="button"
                onClick={() => {
                  setShowAddModal(false);
                }}
                className="px-3 py-1.5 rounded text-xs text-muted-foreground hover:bg-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleCreateRule}
                disabled={!newTitle.trim() || !newDirective.trim()}
                className="px-3.5 py-1.5 rounded bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
              >
                创建并锁定
              </button>
            </div>
          </div>
        </dialog>
      )}
    </section>
  );
};
