'use client';

/**
 * [INPUT] ./useWikiImport::WikiImportController (POS: Obsidian 导入状态、选择器引用与动作)
 * [OUTPUT] WikiObsidianImportCard: “Obsidian vault 导入”卡 (锚点 wiki-obsidian-import): 桌面端选 vault 文件夹, 所有端可上传 ZIP; 导入进行中禁用入口
 * [POS] 总览页的 Obsidian 导入卡; 迁移向导交接的 vault 路径会滚动到此卡并自动导入。
 */

import { useTranslations } from 'next-intl';
import { IconBook, IconDatabase, IconExplore } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import type { WikiImportController } from './useWikiImport';

type WikiObsidianImportCardProps = Pick<
  WikiImportController,
  'isTauriEnv' | 'isImportingObsidian' | 'obsidianZipRef' | 'handleImportObsidianFolder' | 'handleImportObsidianZip'
>;

export function WikiObsidianImportCard({
  isTauriEnv,
  isImportingObsidian,
  obsidianZipRef,
  handleImportObsidianFolder,
  handleImportObsidianZip,
}: WikiObsidianImportCardProps) {
  const t = useTranslations('settings.wiki');

  return (
    <Card id="wiki-obsidian-import">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconBook className="w-5 h-5" />
          {t('import.obsidianTitle')}
        </CardTitle>
        <CardDescription>{t('import.obsidianDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col sm:flex-row gap-4">
        {isTauriEnv && (
          <Button
            onClick={handleImportObsidianFolder}
            disabled={isImportingObsidian}
            variant="outline"
            className="flex-1"
          >
            <IconExplore className="w-4 h-4 mr-2" />
            {isImportingObsidian ? t('import.importing') : t('import.obsidianFolder')}
          </Button>
        )}
        <Button
          onClick={() => obsidianZipRef.current?.click()}
          disabled={isImportingObsidian}
          variant="outline"
          className="flex-1"
        >
          <IconDatabase className="w-4 h-4 mr-2" />
          {isImportingObsidian ? t('import.importing') : t('import.obsidianZip')}
        </Button>
        <input ref={obsidianZipRef} type="file" accept=".zip" onChange={handleImportObsidianZip} className="hidden" />
      </CardContent>
    </Card>
  );
}
