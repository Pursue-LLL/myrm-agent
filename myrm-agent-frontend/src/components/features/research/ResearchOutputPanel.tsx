'use client';

/**
 * [INPUT]
 * @/store/useArtifactPortalStore (POS: Artifact Portal 全局状态)
 * ../artifacts/ArtifactRenderer (POS: Artifact 预览渲染器)
 * ../artifacts/portal/PortalTabs (POS: Artifact 标签页)
 * @/services/wikiService (POS: Wiki API 客户端)
 *
 * [OUTPUT]
 * ResearchOutputPanel: 右栏工件输出面板
 *
 * [POS]
 * Research 右栏输出面板。复用 ArtifactRenderer 展示生成的工件，支持下载和存入 Wiki。
 */

import { useTranslations } from 'next-intl';
import { FileText, Download, BookmarkPlus } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import {
  useActiveTab,
  useArtifactContent,
  useArtifactLoading,
  useIsGenerating,
  useDisplayMode,
  useOpenTabs,
} from '@/store/useArtifactPortalStore';
import ArtifactRenderer from '../artifacts/ArtifactRenderer';
import PortalTabs from '../artifacts/portal/PortalTabs';
import { formatBytes, getDownloadFilename } from '../artifacts/artifactUtils';
import { getStorageUrl } from '@/lib/api';
import { wikiService } from '@/services/wikiService';
import { toast } from 'sonner';
import { useCallback } from 'react';

export default function ResearchOutputPanel() {
  const t = useTranslations('research');
  const activeTab = useActiveTab();
  const content = useArtifactContent();
  const contentLoading = useArtifactLoading();
  const isGenerating = useIsGenerating();
  const displayMode = useDisplayMode();
  const { tabs } = useOpenTabs();

  const handleDownload = useCallback(() => {
    if (!activeTab) return;
    const { artifact } = activeTab;
    const filename = getDownloadFilename(artifact);
    const a = document.createElement('a');
    a.download = filename;

    if (artifact.preview_url) {
      a.href = getStorageUrl(artifact.preview_url);
      a.click();
    } else {
      const blob = new Blob([content], { type: artifact.content_type || 'text/plain' });
      const blobUrl = URL.createObjectURL(blob);
      a.href = blobUrl;
      a.click();
      URL.revokeObjectURL(blobUrl);
    }
  }, [activeTab, content]);

  const handleSaveToWiki = useCallback(async () => {
    if (!activeTab) return;
    try {
      const result = await wikiService.ingestArtifact(activeTab.artifact.id);
      if (result.success) {
        toast.success(t('savedToWiki'));
      } else {
        toast.error(result.message);
      }
    } catch {
      toast.error(t('errors.saveToWikiFailed'));
    }
  }, [activeTab, t]);

  if (tabs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-12 px-4 text-center">
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
          <FileText className="w-6 h-6 text-muted-foreground" />
        </div>
        <p className="text-sm text-muted-foreground">{t('emptyOutput')}</p>
        <p className="text-xs text-muted-foreground mt-1">{t('emptyOutputHint')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      {tabs.length > 1 && (
        <div className="shrink-0 border-b">
          <PortalTabs />
        </div>
      )}

      {/* Content */}
      <ScrollArea className="flex-1 min-h-0">
        {activeTab && (
          <div className="h-full">
            <ArtifactRenderer
              artifact={activeTab.artifact}
              content={content}
              displayMode={displayMode}
              loading={contentLoading}
              onDownload={handleDownload}
            />
          </div>
        )}
      </ScrollArea>

      {/* Action Bar */}
      {activeTab && !isGenerating && (
        <div className="shrink-0 px-3 py-2 border-t flex items-center justify-between gap-2 bg-background">
          <div className="text-xs text-muted-foreground truncate">
            {activeTab.artifact.filename}
            {activeTab.artifact.size != null && (
              <span className="ml-1.5">({formatBytes(activeTab.artifact.size)})</span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleSaveToWiki}>
              <BookmarkPlus className="w-3.5 h-3.5 mr-1" />
              {t('saveToWiki')}
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleDownload}>
              <Download className="w-3.5 h-3.5 mr-1" />
              {t('download')}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
