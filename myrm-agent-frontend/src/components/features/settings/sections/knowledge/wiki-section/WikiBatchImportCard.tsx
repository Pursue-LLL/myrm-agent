'use client';

/**
 * [INPUT] ./useWikiImport::WikiImportController (POS: 导入状态、选择器引用与动作)
 * [OUTPUT] WikiBatchImportCard: “批量导入”卡: 文件夹 / ZIP / 链接 / 视频四个入口与隐藏的文件选择器 (网页端才有文件夹选择器); 导入进行中禁用全部入口
 * [POS] 总览页的批量导入卡; 桌面端用系统对话框选文件夹, 网页端用 webkitdirectory 选择器。
 */

import { useTranslations } from 'next-intl';
import { IconBook, IconDatabase, IconExplore, IconGlow, IconVideo } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import type { WikiImportController } from './useWikiImport';

type WikiBatchImportCardProps = Pick<
  WikiImportController,
  | 'isTauriEnv'
  | 'isImporting'
  | 'zipInputRef'
  | 'webFolderInputRef'
  | 'handleImportFolder'
  | 'handleImportZip'
  | 'handleWebFolderSelect'
  | 'setUrlImportDialogOpen'
  | 'setVideoImportDialogOpen'
>;

export function WikiBatchImportCard({
  isTauriEnv,
  isImporting,
  zipInputRef,
  webFolderInputRef,
  handleImportFolder,
  handleImportZip,
  handleWebFolderSelect,
  setUrlImportDialogOpen,
  setVideoImportDialogOpen,
}: WikiBatchImportCardProps) {
  const t = useTranslations('settings.wiki');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconDatabase className="w-5 h-5" />
          {t('import.title')}
        </CardTitle>
        <CardDescription>{t('import.description')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col sm:flex-row gap-4">
        <Button onClick={handleImportFolder} disabled={isImporting} variant="outline" className="flex-1">
          <IconExplore className="w-4 h-4 mr-2" />
          {isImporting ? t('import.importing') : t('import.folder')}
        </Button>
        <Button
          onClick={() => zipInputRef.current?.click()}
          disabled={isImporting}
          variant="outline"
          className="flex-1"
        >
          <IconBook className="w-4 h-4 mr-2" />
          {isImporting ? t('import.importing') : t('import.zip')}
        </Button>
        <Button
          onClick={() => setUrlImportDialogOpen(true)}
          disabled={isImporting}
          variant="outline"
          className="flex-1"
        >
          <IconGlow className="w-4 h-4 mr-2" />
          {t('import.urls')}
        </Button>
        <Button
          onClick={() => setVideoImportDialogOpen(true)}
          disabled={isImporting}
          variant="outline"
          className="flex-1"
        >
          <IconVideo className="w-4 h-4 mr-2" />
          {t('import.video')}
        </Button>
        <input ref={zipInputRef} type="file" accept=".zip" onChange={handleImportZip} className="hidden" />
        {!isTauriEnv && (
          <input
            ref={webFolderInputRef}
            type="file"
            // @ts-expect-error -- webkitdirectory is non-standard but supported by all major browsers
            webkitdirectory=""
            onChange={handleWebFolderSelect}
            className="hidden"
          />
        )}
      </CardContent>
    </Card>
  );
}
