'use client';

/**
 * [INPUT] ./useMemoryImportExport::MemoryImportExport (POS: 导入导出状态与动作), @/components/primitives/tooltip (POS: 悬浮提示)
 * [OUTPUT] MemoryToolbar: 记忆面板右上角的图标工具栏（导入 / 导出 JSON / 导出 Markdown / 分享规则 / 刷新 / 新建 / 清空）
 * [POS] 记忆面板的操作入口：纯展示，状态与动作全部由父级传入；清空按钮悬浮时使用 destructive 文本色。
 */

import type { ComponentProps, ComponentType } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconDownload,
  IconFileText,
  IconLoader,
  IconPlus,
  IconRefresh,
  IconShieldCheck,
  IconTrash,
  IconUpload,
  type IconProps,
} from '@/components/features/icons/PremiumIcons';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryImportExport } from './useMemoryImportExport';

interface MemoryToolbarProps {
  importExport: MemoryImportExport;
  isRefreshing: boolean;
  onRefresh: () => void;
  onShareRules: () => void;
  onCreate: () => void;
  onClearAll: () => void;
}

function ToolbarButton({ className, ...props }: ComponentProps<'button'>) {
  return (
    <button
      type="button"
      className={cn(
        'p-2 rounded-lg transition-colors hover:bg-accent',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className,
      )}
      {...props}
    />
  );
}

function BusyIcon({ busy, icon: Icon }: { busy: boolean; icon: ComponentType<IconProps> }) {
  return busy ? (
    <IconLoader className="w-[18px] h-[18px] animate-spin text-muted-foreground" />
  ) : (
    <Icon className="w-[18px] h-[18px] text-muted-foreground" />
  );
}

export function MemoryToolbar({
  importExport,
  isRefreshing,
  onRefresh,
  onShareRules,
  onCreate,
  onClearAll,
}: MemoryToolbarProps) {
  const t = useTranslations('memory');
  const {
    importInputRef,
    isImporting,
    isExporting,
    isExportingMd,
    handleImportFile,
    handleExport,
    handleExportMarkdown,
  } = importExport;

  return (
    <div className="flex items-center gap-1">
      <input ref={importInputRef} type="file" accept=".json,.jsonl" onChange={handleImportFile} className="hidden" />
      <ToolbarButton onClick={() => importInputRef.current?.click()} disabled={isImporting} title={t('import')}>
        <BusyIcon busy={isImporting} icon={IconUpload} />
      </ToolbarButton>
      <ToolbarButton onClick={handleExport} disabled={isExporting} title={t('export')}>
        <BusyIcon busy={isExporting} icon={IconDownload} />
      </ToolbarButton>
      <Tooltip>
        <TooltipTrigger asChild>
          <ToolbarButton onClick={handleExportMarkdown} disabled={isExportingMd} title={t('exportMarkdown')}>
            <BusyIcon busy={isExportingMd} icon={IconFileText} />
          </ToolbarButton>
        </TooltipTrigger>
        <TooltipContent>{t('exportMarkdown')}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <ToolbarButton onClick={onShareRules} title={t('shareRulesTitle')}>
            <IconShieldCheck className="w-[18px] h-[18px] text-muted-foreground" />
          </ToolbarButton>
        </TooltipTrigger>
        <TooltipContent>{t('shareRulesTooltip')}</TooltipContent>
      </Tooltip>
      <ToolbarButton onClick={onRefresh} disabled={isRefreshing} title={t('retry')}>
        <IconRefresh className={cn('w-[18px] h-[18px] text-muted-foreground', isRefreshing && 'animate-spin')} />
      </ToolbarButton>
      <ToolbarButton onClick={onCreate} title={t('createDialog.title')}>
        <IconPlus className="w-[18px] h-[18px] text-muted-foreground" />
      </ToolbarButton>
      <ToolbarButton onClick={onClearAll} title={t('clearAll')} className="hover:bg-destructive/10">
        <IconTrash className="w-[18px] h-[18px] text-muted-foreground hover:text-destructive-text" />
      </ToolbarButton>
    </div>
  );
}
