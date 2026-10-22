'use client';

/**
 * [INPUT]
 * - @/components/primitives::{Button, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue}
 * - @/lib/utils/classnameUtils::cn
 * - @/components/features/message-box/progress-steps/toolIcons::{AgentThemeColor, AGENT_COLOR_CLASSES}
 *
 * [OUTPUT]
 * - SubagentCard: 渲染单个临时子代理配置卡片（包含名称、角色范围、主题色、模型覆盖与审查轮次上限）
 *
 * [POS]
 * Agent 编辑面板下的单个 Subagent 配置卡片。支持为每个子代理角色覆盖轻量经济模型以显著降低调用成本。
 */

import React, { memo } from 'react';
import { Trash2, AlertCircle, Cpu } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';
import { type AgentThemeColor, AGENT_COLOR_CLASSES } from '@/components/features/message-box/progress-steps/toolIcons';

export type SubagentControlScope = 'leaf' | 'orchestrator';

export interface EphemeralSubagentConfig {
  display_name?: string;
  theme_color?: AgentThemeColor;
  control_scope?: SubagentControlScope;
  model_override?: string;
  max_review_rounds?: number;
}

const AVAILABLE_COLORS: AgentThemeColor[] = ['blue', 'green', 'purple', 'orange', 'pink', 'cyan', 'amber', 'red'];

const COLOR_HEX: Record<string, string> = {
  blue: '#3b82f6',
  green: '#10b981',
  purple: '#a855f7',
  orange: '#f97316',
  pink: '#ec4899',
  cyan: '#06b6d4',
  amber: '#f59e0b',
  red: '#ef4444',
};

const SUGGESTED_MODELS = [
  { value: 'inherit', label: '跟随主智能体 (Default)' },
  { value: 'deepseek-chat', label: 'DeepSeek-V3 / Flash (推荐·极致低成本)' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini (快速审查)' },
  { value: 'claude-3-5-haiku', label: 'Claude 3.5 Haiku (高吞吐审计)' },
];

export interface SubagentCardProps {
  subagentKey: string;
  config: EphemeralSubagentConfig;
  displayNameError?: string;
  onDisplayNameChange: (key: string, name: string) => void;
  onThemeColorChange: (key: string, color: AgentThemeColor) => void;
  onControlScopeChange: (key: string, scope: SubagentControlScope) => void;
  onModelOverrideChange: (key: string, model: string | undefined) => void;
  onDelete: () => void;
  t: (key: string) => string;
}

export const SubagentCard = memo(function SubagentCard({
  subagentKey,
  config,
  displayNameError,
  onDisplayNameChange,
  onThemeColorChange,
  onControlScopeChange,
  onModelOverrideChange,
  onDelete,
  t,
}: SubagentCardProps) {
  const themeColor = (config.theme_color || 'blue') as AgentThemeColor;
  const currentModel = config.model_override || 'inherit';

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-foreground">{subagentKey}</div>
        <Button
          onClick={onDelete}
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-destructive hover:text-destructive hover:bg-destructive/10 cursor-pointer"
        >
          <Trash2 size={14} />
        </Button>
      </div>

      {/* Display Name */}
      <div className="space-y-1.5">
        <Label htmlFor={`display-name-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentDisplayName')}
        </Label>
        <Input
          id={`display-name-${subagentKey}`}
          value={config.display_name || ''}
          onChange={(e) => onDisplayNameChange(subagentKey, e.target.value)}
          placeholder={t('subagentDisplayNamePlaceholder')}
          className={cn('h-9 text-sm', displayNameError && 'border-destructive focus-visible:ring-destructive')}
        />
        {displayNameError && (
          <div className="flex items-center gap-1.5 text-xs text-destructive">
            <AlertCircle size={12} />
            {displayNameError}
          </div>
        )}
      </div>

      {/* Control Scope */}
      <div className="space-y-1.5">
        <Label htmlFor={`control-scope-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentRole')}
        </Label>
        <Select
          value={config.control_scope || 'leaf'}
          onValueChange={(value) => onControlScopeChange(subagentKey, value as SubagentControlScope)}
        >
          <SelectTrigger id={`control-scope-${subagentKey}`} className="h-9 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="leaf">
              <div className="flex flex-col py-1">
                <span>{t('subagentRoleWorker')}</span>
                <span className="text-xs text-muted-foreground">{t('subagentRoleWorkerDesc')}</span>
              </div>
            </SelectItem>
            <SelectItem value="orchestrator">
              <div className="flex flex-col py-1">
                <span>{t('subagentRoleCoordinator')}</span>
                <span className="text-xs text-muted-foreground">{t('subagentRoleCoordinatorDesc')}</span>
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Model Override (Cost Optimization) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor={`model-override-${subagentKey}`} className="text-xs font-medium text-muted-foreground flex items-center gap-1">
            <Cpu size={12} className="text-primary" />
            <span>模型覆盖 (Model Override)</span>
          </Label>
          <span className="text-[10px] text-muted-foreground/80 bg-primary/10 text-primary px-1.5 py-0.2 rounded font-medium">
            子代理降本
          </span>
        </div>
        <Select
          value={currentModel}
          onValueChange={(value) => onModelOverrideChange(subagentKey, value === 'inherit' ? undefined : value)}
        >
          <SelectTrigger id={`model-override-${subagentKey}`} className="h-9 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SUGGESTED_MODELS.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Theme Color */}
      <div className="space-y-1.5">
        <Label htmlFor={`theme-color-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentThemeColor')}
        </Label>
        <Select value={themeColor} onValueChange={(value) => onThemeColorChange(subagentKey, value as AgentThemeColor)}>
          <SelectTrigger className="h-9 text-sm">
            <SelectValue>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    'w-4 h-4 rounded-full border-2',
                    AGENT_COLOR_CLASSES[themeColor]?.border || AGENT_COLOR_CLASSES.blue.border,
                  )}
                  style={{ backgroundColor: COLOR_HEX[themeColor] || COLOR_HEX.blue }}
                />
                <span className="capitalize">{themeColor}</span>
              </div>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {AVAILABLE_COLORS.map((color) => (
              <SelectItem key={color} value={color}>
                <div className="flex items-center gap-2">
                  <div
                    className={cn('w-4 h-4 rounded-full border-2', AGENT_COLOR_CLASSES[color].border)}
                    style={{ backgroundColor: COLOR_HEX[color] || COLOR_HEX.blue }}
                  />
                  <span className="capitalize">{color}</span>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
});

SubagentCard.displayName = 'SubagentCard';
