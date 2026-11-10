'use client';

/**
 * [INPUT]
 * - @/components/primitives::{Button, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue}
 * - @/components/features/settings/default-model/EnabledModelSelect::EnabledModelSelect
 * - @/store/useProviderStore::useProviderStore
 * - @/lib/utils/classnameUtils::cn
 * - @/components/features/message-box/progress-steps/toolIcons::{AgentThemeColor, AGENT_COLOR_CLASSES}
 *
 * [OUTPUT]
 * - SubagentCard: 渲染单个临时子代理配置卡片（包含名称、角色范围、主题色与模型覆盖）
 *
 * [POS]
 * Agent 编辑面板下的单个 Subagent 配置卡片。模型覆盖的选项来自用户已启用的 provider 模型，按 `providerId/model` 路由名保存，后端据此为该子代理解析专属 LLM。
 */

import React, { memo, useMemo } from 'react';
import { Trash2, AlertCircle, Cpu } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Label } from '@/components/primitives/label';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import EnabledModelSelect from '@/components/features/settings/default-model/EnabledModelSelect';
import useProviderStore, { selectEnabledModels } from '@/store/useProviderStore';
import type { SingleModelSelection } from '@/store/config/providerTypes';
import { cn } from '@/lib/utils/classnameUtils';
import { type AgentThemeColor, AGENT_COLOR_CLASSES } from '@/components/features/message-box/progress-steps/toolIcons';

export type SubagentControlScope = 'leaf' | 'orchestrator';

export interface EphemeralSubagentConfig {
  display_name?: string;
  theme_color?: AgentThemeColor;
  control_scope?: SubagentControlScope;
  /** Routed model name (`providerId/model`); absent means the sub-agent inherits the parent LLM. */
  model?: string;
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

export interface SubagentCardProps {
  subagentKey: string;
  config: EphemeralSubagentConfig;
  displayNameError?: string;
  onDisplayNameChange: (key: string, name: string) => void;
  onThemeColorChange: (key: string, color: AgentThemeColor) => void;
  onControlScopeChange: (key: string, scope: SubagentControlScope) => void;
  onModelChange: (key: string, model: string | undefined) => void;
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
  onModelChange,
  onDelete,
  t,
}: SubagentCardProps) {
  const themeColor = (config.theme_color || 'blue') as AgentThemeColor;
  const providers = useProviderStore((state) => state.providers);
  const enabledModels = useMemo(() => selectEnabledModels(providers), [providers]);
  const selectedModel = useMemo<SingleModelSelection | null>(() => {
    if (!config.model) {
      return null;
    }
    const separator = config.model.indexOf('/');
    if (separator <= 0) {
      return null;
    }
    return { providerId: config.model.slice(0, separator), model: config.model.slice(separator + 1) };
  }, [config.model]);

  return (
    <div className="p-4 rounded-lg border border-border/50 bg-muted/30 space-y-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium text-foreground">{subagentKey}</div>
        <Button
          onClick={onDelete}
          aria-label={t('deleteSubagent')}
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-destructive-text hover:text-destructive-text hover:bg-destructive/10 cursor-pointer"
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
          aria-invalid={displayNameError ? true : undefined}
          aria-describedby={displayNameError ? `display-name-error-${subagentKey}` : undefined}
          className="h-9 text-sm aria-invalid:border-destructive aria-invalid:focus-visible:ring-destructive"
        />
        {displayNameError && (
          <div
            id={`display-name-error-${subagentKey}`}
            role="alert"
            className="flex items-center gap-1.5 text-xs text-destructive-text"
          >
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

      {/* Model (Cost Optimization) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-muted-foreground flex items-center gap-1">
            <Cpu size={12} className="text-primary" />
            <span>{t('modelOverride')}</span>
          </div>
          <span className="text-[10px] text-muted-foreground/80 bg-primary/10 text-primary px-1.5 py-0.2 rounded font-medium">
            {t('subagentCostSaving')}
          </span>
        </div>
        <EnabledModelSelect
          value={selectedModel}
          onChange={(selection) =>
            onModelChange(subagentKey, selection ? `${selection.providerId}/${selection.model}` : undefined)
          }
          enabledModels={enabledModels}
          providers={providers}
          placeholder={t('subagentModelInherit')}
        />
      </div>

      {/* Theme Color */}
      <div className="space-y-1.5">
        <Label htmlFor={`theme-color-${subagentKey}`} className="text-xs font-medium text-muted-foreground">
          {t('subagentThemeColor')}
        </Label>
        <Select value={themeColor} onValueChange={(value) => onThemeColorChange(subagentKey, value as AgentThemeColor)}>
          <SelectTrigger id={`theme-color-${subagentKey}`} className="h-9 text-sm">
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
