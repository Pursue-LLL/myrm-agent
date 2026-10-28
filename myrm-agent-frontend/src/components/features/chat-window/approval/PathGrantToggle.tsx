'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: toolApproval 文案)
 * - @/store/chat/types::ApprovalGrantDirectory (POS: 审批卡片提供的可授权文件夹)
 *
 * [OUTPUT]
 * - PathGrantToggle: 「同时授予文件夹访问」勾选项，并列出将要授权的每个文件夹及其读写范围
 *
 * [POS]
 * 路径审批卡片的目录授权开关；文件夹列表由 harness 规划，卡片只展示不推断。
 */

import { useTranslations } from 'next-intl';
import { useId } from 'react';

import { Badge } from '@/components/primitives/badge';
import { Checkbox } from '@/components/primitives/checkbox';
import type { ApprovalGrantDirectory } from '@/store/chat/types';

interface PathGrantToggleProps {
  directories: ApprovalGrantDirectory[];
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}

export default function PathGrantToggle({ directories, checked, onCheckedChange, disabled }: PathGrantToggleProps) {
  const t = useTranslations('toolApproval');
  const checkboxId = useId();

  return (
    <div className="space-y-1.5 rounded-md border border-border bg-muted/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <Checkbox
          id={checkboxId}
          checked={checked}
          disabled={disabled}
          onCheckedChange={(next) => onCheckedChange(next === true)}
        />
        <label
          htmlFor={checkboxId}
          title={t('grantDirectoryDesc')}
          className="cursor-pointer text-xs font-medium text-foreground"
        >
          {t('grantDirectory')}
        </label>
      </div>
      <ul className="space-y-1 pl-6">
        {directories.map(({ path, writable }) => (
          <li key={path} className="flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
            <span className="min-w-0 flex-1 truncate font-mono" title={path}>
              {path}
            </span>
            <Badge
              variant={writable ? 'outline' : 'secondary'}
              className={`h-4 shrink-0 px-1 text-[10px] ${writable ? 'border-warning/40 bg-warning/10 text-warning' : ''}`}
            >
              {writable ? t('grantDirectoryReadWrite') : t('grantDirectoryReadOnly')}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
