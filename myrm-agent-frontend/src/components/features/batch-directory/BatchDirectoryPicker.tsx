'use client';

/**
 * [INPUT] ./useDirectoryBrowser::DirectoryBrowser (POS: 目录浏览与勾选状态), next-intl (POS: batchDirectory 文案)
 * [OUTPUT] BatchDirectoryPicker: 目录选择器（当前路径条 + 上一级 / 刷新 + 可勾选的子目录列表 + 已选数量）
 * [POS] 创建向导里选择批量目标目录的控件；整行点击切换勾选，行尾箭头进入子目录。
 */

import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight, FolderOpen, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import { Label } from '@/components/primitives/label';
import { cn } from '@/lib/utils/classnameUtils';
import type { DirectoryBrowser } from './useDirectoryBrowser';

export function BatchDirectoryPicker({ dirs }: { dirs: DirectoryBrowser }) {
  const t = useTranslations('batchDirectory');
  const { currentDir, entries, browsing, selected, browse, goUp, toggle } = dirs;

  return (
    <div className="grid gap-1.5">
      <Label>{t('dirsLabel')}</Label>
      <div className="rounded-md border bg-muted/30 p-2 flex items-center gap-2 text-sm">
        <FolderOpen className="size-4 text-muted-foreground shrink-0" />
        <span className="truncate flex-1 font-mono">{currentDir}</span>
        {currentDir !== '~' && (
          <Button variant="ghost" size="sm" onClick={goUp} disabled={browsing}>
            <ChevronLeft className="size-4" />
            {t('browseUp')}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={() => void browse(currentDir)} disabled={browsing}>
          <RefreshCw className={cn('size-4', browsing && 'animate-spin')} />
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-56 overflow-y-auto rounded-md border p-2">
        {entries.length === 0 && (
          <p className="text-sm text-muted-foreground col-span-2 py-4 text-center">{t('browseEmpty')}</p>
        )}
        {entries.map((entry) => {
          const checked = selected.includes(entry.path);
          return (
            // 浏览按钮放在 label 外：label 自带的点击转发只会触发一次勾选（label 内再嵌 onClick 会让鼠标点击被转发为第二次点击，选中立刻被取消）
            <div key={entry.path} className="flex items-stretch rounded-md hover:bg-accent text-sm">
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-2">
                <Checkbox checked={checked} onCheckedChange={() => toggle(entry.path)} />
                <span className={cn('truncate flex-1', checked && 'font-medium')}>{entry.name}</span>
              </label>
              <Button
                variant="ghost"
                size="sm"
                className="size-7 my-1.5 mr-2"
                onClick={() => void browse(entry.path)}
                aria-label={t('browseInto')}
              >
                <ChevronRight className="size-3.5" />
              </Button>
            </div>
          );
        })}
      </div>
      {selected.length > 0 && (
        <p className="text-xs text-muted-foreground">{t('dirsSelectedCount', { count: selected.length })}</p>
      )}
    </div>
  );
}
