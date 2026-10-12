/**
 * [INPUT]
 * @/services/memory/autoMemoryConsolidation::AutoMemoryGatingConfigDTO
 * lucide-react::Sliders, RotateCcw, Check
 *
 * [OUTPUT]
 * GatingRulesConfigView: Config editor for auto-consolidation idle & budget thresholds.
 *
 * [POS]
 * Threshold customization panel for Item 123 auto-consolidation studio.
 * Strict typing: No `any`. Single file < 250 lines.
 */

import React, { useState } from 'react';
import { Sliders, RotateCcw, Check } from 'lucide-react';
import type { AutoMemoryGatingConfigDTO } from '@/services/memory/autoMemoryConsolidation';
import { FALLBACK_AUTO_CONSOLIDATION_CONFIG } from './autoMemoryConsolidationFallbacks';

interface GatingRulesConfigViewProps {
  config: AutoMemoryGatingConfigDTO;
  onSaveConfig: (updated: AutoMemoryGatingConfigDTO) => Promise<void>;
  disabled?: boolean;
}

export const GatingRulesConfigView: React.FC<GatingRulesConfigViewProps> = ({
  config,
  onSaveConfig,
  disabled = false,
}) => {
  const [formData, setFormData] = useState<AutoMemoryGatingConfigDTO>({ ...config });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleReset = () => {
    setFormData({ ...FALLBACK_AUTO_CONSOLIDATION_CONFIG });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      await onSaveConfig(formData);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="自动记忆沉淀双门禁参数配置面板"
      className="space-y-4 p-4 rounded-lg bg-card/60 border border-border/40 text-xs"
    >
      <div className="flex items-center justify-between pb-2 border-b border-border/30">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-primary" />
          <span className="font-semibold text-foreground text-sm">
            双门禁准入与闲置自适应阈值配置
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleReset}
            disabled={disabled || isSaving}
            aria-label="恢复默认门禁配置"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-secondary/60 hover:bg-secondary text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            <RotateCcw className="w-3 h-3" />
            恢复默认
          </button>
          <button
            type="submit"
            disabled={disabled || isSaving}
            aria-label="保存自动记忆门禁配置"
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            {saveSuccess ? (
              <>
                <Check className="w-3 h-3 text-emerald-400" />
                已保存
              </>
            ) : isSaving ? (
              '保存中...'
            ) : (
              '应用配置'
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 全局开关 */}
        <div className="flex items-center justify-between p-2.5 rounded bg-muted/30 border border-border/30 col-span-1 md:col-span-2">
          <label htmlFor="auto-memory-enabled" className="font-medium text-foreground cursor-pointer">
            启用后台自适应记忆提炼引擎
            <span className="block text-[11px] text-muted-foreground font-normal">
              关闭后将暂停一切后台自主记忆抽取，仅在手动指令下允许提取。
            </span>
          </label>
          <input
            id="auto-memory-enabled"
            type="checkbox"
            checked={formData.enabled}
            onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
            disabled={disabled || isSaving}
            aria-label="启用后台自适应记忆提炼引擎"
            className="w-4 h-4 rounded border-border focus:ring-2 focus:ring-primary text-primary"
          />
        </div>

        {/* 闲置超时时长 */}
        <div className="space-y-1.5">
          <label htmlFor="cfg-idle-timeout" className="font-medium text-foreground block">
            会话闲置触发时长 (秒)
          </label>
          <input
            id="cfg-idle-timeout"
            type="number"
            min={10}
            max={7200}
            step={10}
            value={formData.idle_timeout_seconds}
            onChange={(e) =>
              setFormData({ ...formData, idle_timeout_seconds: Number(e.target.value) })
            }
            disabled={disabled || isSaving}
            aria-label="会话闲置触发时长"
            className="w-full px-2.5 py-1.5 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="text-[11px] text-muted-foreground">默认 900 秒 (15 分钟)，非活动期间低优先级唤醒。</p>
        </div>

        {/* 最小有效对话轮数 */}
        <div className="space-y-1.5">
          <label htmlFor="cfg-min-turns" className="font-medium text-foreground block">
            最小对话轮数门禁 (Turns)
          </label>
          <input
            id="cfg-min-turns"
            type="number"
            min={1}
            max={20}
            value={formData.min_turn_count}
            onChange={(e) =>
              setFormData({ ...formData, min_turn_count: Number(e.target.value) })
            }
            disabled={disabled || isSaving}
            aria-label="最小对话轮数门禁"
            className="w-full px-2.5 py-1.5 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="text-[11px] text-muted-foreground">低于该轮数视为短对话直接跳过，杜绝垃圾碎片。</p>
        </div>

        {/* 最小信息密度 */}
        <div className="space-y-1.5">
          <label htmlFor="cfg-min-info-density" className="font-medium text-foreground block">
            信息密度门禁阈值 (0.0 ~ 1.0)
          </label>
          <input
            id="cfg-min-info-density"
            type="number"
            min={0.0}
            max={1.0}
            step={0.05}
            value={formData.min_info_density}
            onChange={(e) =>
              setFormData({ ...formData, min_info_density: Number(e.target.value) })
            }
            disabled={disabled || isSaving}
            aria-label="信息密度门禁阈值"
            className="w-full px-2.5 py-1.5 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="text-[11px] text-muted-foreground">基于停用词与词汇丰富度判定，过滤纯问候与客套闲聊。</p>
        </div>

        {/* 剩余 Token 保护底线 */}
        <div className="space-y-1.5">
          <label htmlFor="cfg-min-budget-floor" className="font-medium text-foreground block">
            Token 额度保护安全底线 (Tokens)
          </label>
          <input
            id="cfg-min-budget-floor"
            type="number"
            min={100}
            max={50000}
            step={100}
            value={formData.min_remaining_budget_tokens}
            onChange={(e) =>
              setFormData({ ...formData, min_remaining_budget_tokens: Number(e.target.value) })
            }
            disabled={disabled || isSaving}
            aria-label="Token 额度保护安全底线"
            className="w-full px-2.5 py-1.5 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="text-[11px] text-muted-foreground">当可用 Token 低于此门槛时自动挂起，保护用户主线预算。</p>
        </div>

        {/* 提炼开销占比上限 */}
        <div className="space-y-1.5 col-span-1 md:col-span-2">
          <label htmlFor="cfg-max-cost-ratio" className="font-medium text-foreground block">
            提炼消耗占剩余预算比例上限 (0.0 ~ 1.0)
          </label>
          <input
            id="cfg-max-cost-ratio"
            type="number"
            min={0.05}
            max={1.0}
            step={0.05}
            value={formData.max_consolidation_cost_ratio}
            onChange={(e) =>
              setFormData({ ...formData, max_consolidation_cost_ratio: Number(e.target.value) })
            }
            disabled={disabled || isSaving}
            aria-label="提炼消耗占剩余预算比例上限"
            className="w-full px-2.5 py-1.5 rounded border border-border/60 bg-background text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <p className="text-[11px] text-muted-foreground">防止提炼任务反客为主（默认单次提炼不能超过剩余预算的 25%）。</p>
        </div>
      </div>
    </form>
  );
};
