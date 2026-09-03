'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { FolderArchive, Download, Eye, Layers, Sparkles, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { DeliverableManifest } from './deliverableTypes';
import { DeliverablesBoard } from './DeliverablesBoard';
import { formatBytes } from './artifactUtils';
import { getApiUrl } from '@/lib/api';

interface DeliverableBundleCardProps {
  manifest: DeliverableManifest;
}

export const DeliverableBundleCard: React.FC<DeliverableBundleCardProps> = ({ manifest }) => {
  const [boardOpen, setBoardOpen] = useState(false);

  const totalSize = manifest.items.reduce((acc, i) => acc + (i.size_bytes || 0), 0);
  const categoriesCount = new Set(manifest.items.map((i) => i.category)).size;

  const handleDownloadZip = (e: React.MouseEvent) => {
    e.stopPropagation();
    const downloadUrl = `${getApiUrl()}/api/v1/files/artifacts/bundles/${manifest.bundle_id}/zip`;
    window.open(downloadUrl, '_blank');
  };

  return (
    <>
      <div
        onClick={() => setBoardOpen(true)}
        className="my-3 p-4 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/5 via-primary/[0.02] to-transparent hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-primary/10 text-primary">
              <FolderArchive className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="font-semibold text-sm text-foreground">{manifest.title || '任务成套交付物包'}</h4>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="w-3 h-3" />
                  已就绪 ({manifest.items.length} 份成品)
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                涵盖 {categoriesCount} 个品类 · 总大小 {formatBytes(totalSize)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setBoardOpen(true)}
              className="h-8 text-xs flex items-center gap-1.5"
            >
              <Eye className="w-3.5 h-3.5" />
              查看看板
            </Button>
            <Button
              size="sm"
              variant="default"
              onClick={handleDownloadZip}
              className="h-8 text-xs flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              打包下载
            </Button>
          </div>
        </div>
      </div>

      <DeliverablesBoard manifest={manifest} open={boardOpen} onOpenChange={setBoardOpen} />
    </>
  );
};
