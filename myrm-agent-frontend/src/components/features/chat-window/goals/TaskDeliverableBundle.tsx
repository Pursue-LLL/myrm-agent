'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Download, ExternalLink, Package } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { fetchWithTimeout, getStorageUrl } from '@/lib/api';
import { toast } from 'sonner';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import type { GoalState } from './goalStatusTypes';
import { getArtifactIcon } from '@/components/features/artifacts/artifactUtils';
import type { ArtifactType } from '@/store/chat/types/artifacts';

interface TaskDeliverableBundleProps {
  goal: GoalState;
  chatId: string;
}

function inferArtifactType(filename: string): ArtifactType {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const typeMap: Record<string, ArtifactType> = {
    xlsx: 'spreadsheet', xls: 'spreadsheet', csv: 'spreadsheet',
    pptx: 'presentation', ppt: 'presentation',
    docx: 'word_document', doc: 'word_document',
    pdf: 'pdf',
    html: 'html', htm: 'html',
    svg: 'svg',
    png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image',
    mp4: 'video', webm: 'video',
    mp3: 'audio', wav: 'audio',
    mmd: 'mermaid',
  };
  return typeMap[ext] ?? 'document';
}

function inferContentType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const mimeMap: Record<string, string> = {
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel',
    csv: 'text/csv',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    ppt: 'application/vnd.ms-powerpoint',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    pdf: 'application/pdf',
    html: 'text/html', htm: 'text/html',
    svg: 'image/svg+xml',
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp',
    mp4: 'video/mp4', webm: 'video/webm',
    mp3: 'audio/mpeg', wav: 'audio/wav',
    mmd: 'text/x-mermaid',
    md: 'text/markdown', txt: 'text/plain',
    json: 'application/json',
  };
  return mimeMap[ext] ?? 'application/octet-stream';
}

export function TaskDeliverableBundle({ goal, chatId }: TaskDeliverableBundleProps) {
  const t = useTranslations('Goal');
  const [downloading, setDownloading] = useState(false);
  const openArtifact = useArtifactPortalStore((s) => s.openArtifact);

  const deliverables = goal.deliverables;

  const handleDownloadAll = useCallback(async () => {
    if (!deliverables) {return;}
    setDownloading(true);
    try {
      const ids = deliverables.map((d) => d.id);
      const res = await fetchWithTimeout('/artifacts/download-bundle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artifact_ids: ids, chat_id: chatId }),
      });
      if (!res.ok) {
        toast.error(t('bundleDownloadFailed'));
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `deliverables-${chatId.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      toast.error(t('bundleDownloadFailed'));
    } finally {
      setDownloading(false);
    }
  }, [deliverables, chatId, t]);

  const handlePreview = useCallback(
    (item: { id: string; filename: string }) => {
      openArtifact({
        id: item.id,
        filename: item.filename,
        type: inferArtifactType(item.filename),
        content_type: inferContentType(item.filename),
        size: 0,
        preview_url: getStorageUrl(`/artifacts/${item.id}/content`),
        download_url: getStorageUrl(`/artifacts/${item.id}/download`),
      });
    },
    [openArtifact],
  );

  if (!deliverables || deliverables.length < 2) {
    return null;
  }
  if (goal.status !== 'complete') {
    return null;
  }

  return (
    <div className="mt-3 rounded-lg border bg-card p-3 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Package className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{t('deliverableBundle')}</span>
          <span className="text-xs text-muted-foreground px-1.5 py-0.5 bg-muted rounded-full">
            {deliverables.length}
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs gap-1"
          onClick={handleDownloadAll}
          disabled={downloading}
        >
          <Download className="h-3 w-3" />
          {downloading ? t('bundleDownloading') : t('bundleDownloadAll')}
        </Button>
      </div>

      <div className="grid gap-1.5 sm:grid-cols-2">
        {deliverables.map((item) => {
          const type = inferArtifactType(item.filename);
          const Icon = getArtifactIcon(type, item.filename);
          return (
            <button
              key={item.id}
              onClick={() => handlePreview(item)}
              className="flex items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs hover:bg-muted/50 transition-colors group"
            >
              <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
              <span className="truncate flex-1 text-foreground">{item.filename}</span>
              <ExternalLink className="h-3 w-3 flex-shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
