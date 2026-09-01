'use client';

import React, { useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Archive,
  Download,
  FolderArchive,
  FileText,
  FileSpreadsheet,
  Image as ImageIcon,
  Film,
  CheckCircle2,
  ExternalLink,
  Layers,
  X,
  Search,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { DeliverableManifest, DeliverableItem, DeliverableCategory } from './deliverableTypes';
import { formatBytes } from './artifactUtils';
import { getApiUrl } from '@/lib/api';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { Artifact } from '@/store/chat/types';

interface DeliverablesBoardProps {
  manifest: DeliverableManifest;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const CATEGORY_LABELS: Record<DeliverableCategory, { zh: string; en: string; icon: any }> = {
  article: { zh: '长文专栏', en: 'Articles', icon: FileText },
  social_post: { zh: '社交短图文', en: 'Social Posts', icon: FileText },
  script: { zh: '分镜与脚本', en: 'Scripts', icon: Film },
  data_sheet: { zh: '排期与数据表', en: 'Data Sheets', icon: FileSpreadsheet },
  visual_asset: { zh: '视觉与封面', en: 'Visual Assets', icon: ImageIcon },
  report: { zh: '分析报告', en: 'Reports', icon: FileText },
  fact_check: { zh: '事实核查表', en: 'Fact Check', icon: CheckCircle2 },
  code_asset: { zh: '代码与脚本', en: 'Code Assets', icon: Layers },
  presentation: { zh: '演示幻灯片', en: 'Slides', icon: Layers },
  other: { zh: '其他产物', en: 'Others', icon: Archive },
};

export const DeliverablesBoard: React.FC<DeliverablesBoardProps> = ({ manifest, open, onOpenChange }) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const { openPortalWithArtifact } = useArtifactPortalStore();

  const categories = useMemo(() => {
    const cats = new Set<DeliverableCategory>();
    manifest.items.forEach((item) => cats.add(item.category));
    return Array.from(cats);
  }, [manifest.items]);

  const filteredItems = useMemo(() => {
    return manifest.items.filter((item) => {
      const matchCategory = selectedCategory === 'all' || item.category === selectedCategory;
      const matchKeyword =
        !searchKeyword ||
        item.title.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        item.relative_path.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        (item.description && item.description.toLowerCase().includes(searchKeyword.toLowerCase()));
      return matchCategory && matchKeyword;
    });
  }, [manifest.items, selectedCategory, searchKeyword]);

  const handleDownloadAllZip = () => {
    const downloadUrl = `${getApiUrl()}/api/v1/files/artifacts/bundles/${manifest.bundle_id}/zip`;
    window.open(downloadUrl, '_blank');
  };

  const handlePreviewItem = (item: DeliverableItem) => {
    // 转换为基础 Artifact 格式并唤起 Portal
    const syntheticArtifact: Artifact = {
      id: item.id,
      type: (item.mime_type?.includes('image') ? 'image' : 'document') as any,
      filename: item.title,
      size: item.size_bytes || 0,
      url: `/api/v1/files/vault/${item.vault_uri.replace('vault://', '')}`,
      created_at: new Date(manifest.created_at * 1000).toISOString(),
    };
    openPortalWithArtifact(syntheticArtifact);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 overflow-hidden bg-background">
        <DialogHeader className="p-6 pb-4 border-b bg-muted/20 flex flex-row items-center justify-between">
          <div className="space-y-1">
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <FolderArchive className="w-6 h-6 text-primary" />
              {manifest.title || '任务交付物全景看板'}
            </DialogTitle>
            <p className="text-xs text-muted-foreground">
              共包含 {manifest.items.length} 份交付物 · 总大小 {formatBytes(manifest.items.reduce((acc, i) => acc + (i.size_bytes || 0), 0))}
            </p>
          </div>
          <Button onClick={handleDownloadAllZip} className="flex items-center gap-2" variant="default">
            <Download className="w-4 h-4" />
            一键打包下载 (ZIP)
          </Button>
        </DialogHeader>

        {/* Toolbar & Filter */}
        <div className="p-4 border-b flex flex-wrap items-center justify-between gap-3 bg-background">
          <div className="flex items-center gap-1.5 overflow-x-auto py-1">
            <Button
              size="sm"
              variant={selectedCategory === 'all' ? 'default' : 'outline'}
              onClick={() => setSelectedCategory('all')}
              className="rounded-full text-xs"
            >
              全部 ({manifest.items.length})
            </Button>
            {categories.map((cat) => {
              const meta = CATEGORY_LABELS[cat] || CATEGORY_LABELS.other;
              const count = manifest.items.filter((i) => i.category === cat).length;
              return (
                <Button
                  key={cat}
                  size="sm"
                  variant={selectedCategory === cat ? 'default' : 'outline'}
                  onClick={() => setSelectedCategory(cat)}
                  className="rounded-full text-xs flex items-center gap-1.5"
                >
                  <meta.icon className="w-3.5 h-3.5" />
                  {meta.zh} ({count})
                </Button>
              );
            })}
          </div>

          <div className="relative w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchKeyword}
              onChange={(e) => setSearchKeyword(e.target.value)}
              placeholder="搜索交付物名称或路径..."
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>

        {/* Grid List */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredItems.map((item) => {
            const meta = CATEGORY_LABELS[item.category] || CATEGORY_LABELS.other;
            return (
              <div
                key={item.id}
                onClick={() => handlePreviewItem(item)}
                className="group p-4 border rounded-xl bg-card hover:border-primary/50 hover:shadow-md transition-all cursor-pointer flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary">
                      <meta.icon className="w-3 h-3" />
                      {meta.zh}
                    </span>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {formatBytes(item.size_bytes || 0)}
                    </span>
                  </div>
                  <h4 className="font-semibold text-sm text-foreground group-hover:text-primary transition-colors line-clamp-1">
                    {item.title}
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {item.description || item.relative_path}
                  </p>
                </div>

                <div className="mt-4 pt-2 border-t flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-mono text-[10px] truncate max-w-[200px]">{item.relative_path}</span>
                  <span className="flex items-center gap-1 text-primary text-[11px] font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    <ExternalLink className="w-3 h-3" /> 预览
                  </span>
                </div>
              </div>
            );
          })}

          {filteredItems.length === 0 && (
            <div className="col-span-full py-16 text-center text-muted-foreground text-xs">
              未找到匹配的交付物
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
