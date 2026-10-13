/**
 * 智能体批量导出 - 步骤一：智能体选择与命名面板
 *
 * [INPUT]
 * @/components/features/icons/PremiumIcons::IconSearch,IconCheck,IconAlertTriangle (POS: 图标资产)
 * @/components/primitives/input::Input (POS: 文本输入框)
 * @/components/primitives/button::Button (POS: 按钮原子组件)
 * @/components/primitives/badge::Badge (POS: 徽标组件)
 * @/components/primitives/alert::Alert,AlertTitle,AlertDescription (POS: 警告信息框)
 * @/services/agent::AgentListItem (POS: 智能体列表项接口)
 * @/components/agent/builtin-agent-i18n::getBuiltinAgentName,getBuiltinAgentDescription (POS: 智能体国际化解析)
 *
 * [OUTPUT]
 * BulkExportSelectStep 组件：提供智能体检索、多选勾选、包名配置与选择统计。
 *
 * [POS]
 * 批量导出向导的第一步交互面板，负责筛选待导出的智能体集合与包标识命名。
 */

'use client';

import { memo, useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';

import { IconAlertTriangle, IconCheck, IconSearch } from '@/components/features/icons/PremiumIcons';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import { getBuiltinAgentDescription, getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import type { AgentListItem } from '@/services/agent';

interface BulkExportSelectStepProps {
  customAgents: AgentListItem[];
  selectedIds: string[];
  searchQuery: string;
  bundleName: string;
  loadFailureText: string | null;
  onSearchChange: (query: string) => void;
  onBundleNameChange: (name: string) => void;
  onToggleSelect: (id: string) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
}

const BulkExportSelectStep = memo(
  ({
    customAgents,
    selectedIds,
    searchQuery,
    bundleName,
    loadFailureText,
    onSearchChange,
    onBundleNameChange,
    onToggleSelect,
    onSelectAll,
    onClearAll,
  }: BulkExportSelectStepProps) => {
    const t = useTranslations('agent.expertExport');
    const locale = useLocale();

    const filteredAgents = useMemo(() => {
      if (!searchQuery.trim()) {
        return customAgents;
      }
      const q = searchQuery.toLowerCase();
      return customAgents.filter((agent) => {
        const name = getBuiltinAgentName(agent.id, agent.name, locale).toLowerCase();
        const desc = getBuiltinAgentDescription(agent.id, agent.description || '', locale).toLowerCase();
        return name.includes(q) || desc.includes(q);
      });
    }, [customAgents, searchQuery, locale]);

    return (
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2">
          <div className="relative flex-1">
            <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('bulk.search')}
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="pl-9 h-9"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onSelectAll}>
              {t('bulk.selectAll')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClearAll}>
              {t('bulk.clear')}
            </Button>
            <Badge variant="secondary" className="font-mono">
              {t('bulk.selectedCount', { selected: selectedIds.length, total: customAgents.length })}
            </Badge>
          </div>
        </div>

        <div>
          <Input
            placeholder={t('bulk.bundleName')}
            value={bundleName}
            onChange={(e) => onBundleNameChange(e.target.value)}
            className="h-9"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border divide-y max-h-[42vh]">
          {filteredAgents.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">{t('bulk.empty')}</div>
          ) : (
            filteredAgents.map((agent) => {
              const isSelected = selectedIds.includes(agent.id);
              return (
                <label
                  key={agent.id}
                  className={cn(
                    'flex items-center justify-between p-3 cursor-pointer transition-colors hover:bg-muted/50 select-none',
                    isSelected && 'bg-primary/5',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggleSelect(agent.id)}
                    className="sr-only"
                    aria-label={getBuiltinAgentName(agent.id, agent.name, locale)}
                  />
                  <div className="flex flex-col gap-0.5 min-w-0 pr-3">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-sm font-medium truncate">
                        {getBuiltinAgentName(agent.id, agent.name, locale)}
                      </span>
                      {agent.subagent_ids && agent.subagent_ids.length > 0 && (
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 py-0 font-normal shrink-0 text-muted-foreground border-border/60"
                        >
                          {t('bulk.subagents', { count: agent.subagent_ids.length })}
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground line-clamp-1">
                      {getBuiltinAgentDescription(agent.id, agent.description || '', locale) || t('bulk.noDescription')}
                    </span>
                  </div>
                  <div
                    className={cn(
                      'h-5 w-5 rounded border flex items-center justify-center shrink-0 transition-colors',
                      isSelected ? 'bg-primary border-primary text-primary-foreground' : 'border-border',
                    )}
                  >
                    {isSelected && <IconCheck className="h-3.5 w-3.5 stroke-[3]" />}
                  </div>
                </label>
              );
            })
          )}
        </div>

        {loadFailureText && (
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>{t('previewFailed')}</AlertTitle>
            <AlertDescription>{loadFailureText}</AlertDescription>
          </Alert>
        )}
      </div>
    );
  },
);

BulkExportSelectStep.displayName = 'BulkExportSelectStep';

export default BulkExportSelectStep;
