'use client';

import { useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Download, ExternalLink, FolderArchive, Layers } from 'lucide-react';
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

export type DeliverableCategory =
  | 'all'
  | 'strategy'
  | 'copywriting'
  | 'visual'
  | 'data_sheet'
  | 'fact_check'
  | 'schedule'
  | 'code'
  | 'other';

function inferDeliverableCategory(filename: string): DeliverableCategory {
  const lower = filename.toLowerCase();
  if (lower.includes('fact_check') || lower.includes('factcheck') || lower.includes('verification') || lower.includes('audit')) {
    return 'fact_check';
  }
  if (lower.includes('schedule') || lower.includes('calendar') || lower.includes('timeline') || lower.includes('plan_7days')) {
    return 'schedule';
  }
  if (lower.includes('strategy') || lower.includes('proposal') || lower.includes('brief') || lower.includes('summary') || lower.includes('report')) {
    return 'strategy';
  }
  if (lower.includes('wechat') || lower.includes('xhs') || lower.includes('xiaohongshu') || lower.includes('douyin') || lower.includes('script') || lower.includes('copy') || lower.includes('article') || lower.includes('post')) {
    return 'copywriting';
  }
  if (/\.(png|jpg|jpeg|svg|webp|gif|mp4|webm|mp3|wav)$/i.test(lower)) {
    return 'visual';
  }
  if (/\.(xlsx|xls|csv)$/i.test(lower)) {
    return 'data_sheet';
  }
  if (/\.(py|ts|js|sh|sql|rs|go)$/i.test(lower)) {
    return 'code';
  }
  return 'other';
}

function inferArtifactType(filename: string): ArtifactType {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const typeMap: Record<string, ArtifactType> = {
    xlsx: 'spreadsheet',
    xls: 'spreadsheet',
    csv: 'spreadsheet',
    pptx: 'presentation',
    ppt: 'presentation',
    docx: 'word_document',
    doc: 'word_document',
    pdf: 'pdf',
    html: 'html',
    htm: 'html',
    svg: 'svg',
    png: 'image',
    jpg: 'image',
    jpeg: 'image',
    gif: 'image',
    webp: 'image',
    mp4: 'video',
    webm: 'video',
    mp3: 'audio',
    wav: 'audio',
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
    html: 'text/html',
    htm: 'text/html',
    svg: 'image/svg+xml',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    mp4: 'video/mp4',
    webm: 'video/webm',
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    mmd: 'text/x-mermaid',
    md: 'text/markdown',
    txt: 'text/plain',
    json: 'application/json',
  };
  return mimeMap[ext] ?? 'application/octet-stream';
}

export function TaskDeliverableBundle({ goal, chatId }: TaskDeliverableBundleProps) {
  const t = useTranslations('Goal');
  const [downloading, setDownloading] = useState(false);
  const [activeCategory, setActiveCategory] = useState<DeliverableCategory>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const openArtifact = useArtifactPortalStore((s) => s.openArtifact);

  const deliverables = goal.deliverables;

  // Enrich items with inferred categories
  const enrichedItems = useMemo(() => {
    if (!deliverables) return [];
    return deliverables.map((d) => ({
      ...d,
      category: inferDeliverableCategory(d.filename),
    }));
  }, [deliverables]);

  // Categories present in deliverables
  const availableCategories = useMemo(() => {
    const cats = new Set<DeliverableCategory>(['all']);
    enrichedItems.forEach((item) => cats.add(item.category));
    return Array.from(cats);
  }, [enrichedItems]);

  const filteredItems = useMemo(() => {
    if (activeCategory === 'all') return enrichedItems;
    return enrichedItems.filter((item) => item.category === activeCategory);
  }, [enrichedItems, activeCategory]);

  const handleDownloadZip = useCallback(
    async (idsToDownload: string[]) => {
      if (!idsToDownload.length) return;
      setDownloading(true);
      try {
        const res = await fetchWithTimeout('/artifacts/download-bundle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artifact_ids: idsToDownload, chat_id: chatId }),
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
    },
    [chatId, t],
  );

  const handleDownloadAll = useCallback(() => {
    if (!deliverables) return;
    handleDownloadZip(deliverables.map((d) => d.id));
  }, [deliverables, handleDownloadZip]);

  const handleDownloadSelected = useCallback(() => {
    if (!selectedIds.size) return;
    handleDownloadZip(Array.from(selectedIds));
  }, [selectedIds, handleDownloadZip]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

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

  const categoryLabelMap: Record<DeliverableCategory, string> = {
    all: t('bundleCategoryAll', { defaultMessage: '全部' }),
    strategy: t('bundleCategoryStrategy', { defaultMessage: '策略与方案' }),
    copywriting: t('bundleCategoryCopywriting', { defaultMessage: '文案与内容' }),
    visual: t('bundleCategoryVisual', { defaultMessage: '视觉与多媒体' }),
    data_sheet: t('bundleCategoryDataSheet', { defaultMessage: '数据与表格' }),
    fact_check: t('bundleCategoryFactCheck', { defaultMessage: '事实核查' }),
    schedule: t('bundleCategorySchedule', { defaultMessage: '排期与规划' }),
    code: t('bundleCategoryCode', { defaultMessage: '代码与脚本' }),
    other: t('bundleCategoryOther', { defaultMessage: '其他资产' }),
  };

  return (
    <div className="mt-3 rounded-lg border bg-card p-3 shadow-sm">
      {/* Header bar */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <FolderArchive className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{t('deliverableBundle')}</span>
          <span className="text-xs text-muted-foreground px-1.5 py-0.5 bg-muted rounded-full">
            {deliverables.length}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {selectedIds.size > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs gap-1 text-primary border-primary/30"
              onClick={handleDownloadSelected}
              disabled={downloading}
            >
              <Download className="h-3 w-3" />
              {t('bundleExportSelected', { count: selectedIds.size, defaultMessage: `导出选中 (${selectedIds.size})` })}
            </Button>
          )}
          <Button
            variant="default"
            size="sm"
            className="h-7 px-2 text-xs gap-1"
            onClick={handleDownloadAll}
            disabled={downloading}
          >
            <Download className="h-3 w-3" />
            {downloading ? t('bundleDownloading') : t('bundleDownloadAll')}
          </Button>
        </div>
      </div>

      {/* Category filter tabs if multiple categories exist */}
      {availableCategories.length > 2 && (
        <div className="flex items-center gap-1 mb-2.5 overflow-x-auto pb-1 text-xs">
          {availableCategories.map((cat) => {
            const count = cat === 'all' ? enrichedItems.length : enrichedItems.filter((i) => i.category === cat).length;
            const isActive = activeCategory === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat)}
                className={`px-2 py-0.5 rounded-full whitespace-nowrap transition-colors flex items-center gap-1 ${
                  isActive
                    ? 'bg-primary text-primary-foreground font-medium'
                    : 'bg-muted/70 text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                <span>{categoryLabelMap[cat]}</span>
                <span className="text-[10px] opacity-80">({count})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Deliverable item grid */}
      <div className="grid gap-1.5 sm:grid-cols-2">
        {filteredItems.map((item) => {
          const type = inferArtifactType(item.filename);
          const Icon = getArtifactIcon(type, item.filename);
          const isSelected = selectedIds.has(item.id);

          return (
            <div
              key={item.id}
              className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors group ${
                isSelected ? 'bg-primary/5 border-primary/40' : 'hover:bg-muted/50 border-border'
              }`}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => toggleSelect(item.id)}
                className="h-3.5 w-3.5 rounded border-muted-foreground/40 text-primary focus:ring-primary cursor-pointer"
                title="Select item for export"
              />
              <button
                type="button"
                onClick={() => handlePreview(item)}
                className="flex items-center gap-2 flex-1 truncate text-left"
              >
                <Icon className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <span className="truncate flex-1 text-foreground">{item.filename}</span>
                <ExternalLink className="h-3 w-3 flex-shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
