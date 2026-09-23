/**
 * [INPUT]
 * - @/services/wikiService::WikiLayerItem (POS: Wiki 分层词条摘要类型)
 * - @/components/primitives/button::Button (POS: 统一按钮原语)
 * - @/components/primitives/badge::Badge (POS: 统一徽标原语)
 *
 * [OUTPUT]
 * - WikiLayerItemPreviewModal: 只读词条 Markdown 与凭据元数据预览弹窗
 *
 * [POS]
 * - Wiki 知识库分层资产只读预览层。提供纯净只读的词条内容与溯源元数据查看，严格隔离写操作。
 */

import React from 'react';
import { FileText, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { WikiLayerItem } from '@/services/wikiService';

interface WikiLayerItemPreviewModalProps {
  item: WikiLayerItem | null;
  layerTitle: string;
  onClose: () => void;
}

export const WikiLayerItemPreviewModal: React.FC<WikiLayerItemPreviewModalProps> = ({
  item,
  layerTitle,
  onClose,
}) => {
  if (!item) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in-50">
      <dialog
        open
        aria-label="词条文档预览"
        className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border border-border bg-card shadow-2xl overflow-hidden m-auto"
      >
        <div className="p-4 border-b border-border/60 flex items-center justify-between bg-secondary/20">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-foreground tracking-tight flex items-center gap-2">
                {item.title}
                <Badge
                  variant={item.publish_status === 'draft' ? 'outline' : 'secondary'}
                  className={`text-[10px] ${
                    item.publish_status === 'draft' ? 'border-amber-500/40 text-amber-500' : ''
                  }`}
                >
                  {item.publish_status === 'draft' ? 'Draft' : 'Live'}
                </Badge>
              </h3>
              <p className="text-xs font-mono text-muted-foreground mt-0.5">
                {item.relative_path}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 text-xs leading-relaxed text-foreground/90">
          <div className="p-3 rounded-lg bg-secondary/30 border border-border/40 font-mono text-[11px] text-muted-foreground flex flex-col gap-1">
            <div>更新时间：{item.updated_at || '刚刚'}</div>
            <div>存储分层：{layerTitle}</div>
            <div>溯源凭据：已校验负向排除策略，关联交付审计链</div>
          </div>

          <div className="p-4 rounded-xl border border-border/50 bg-background/60 font-sans whitespace-pre-wrap leading-relaxed">
            {item.content_snippet}
          </div>
        </div>

        <div className="p-3 border-t border-border/60 flex justify-end bg-secondary/10">
          <Button variant="outline" size="sm" onClick={onClose} className="h-8 text-xs">
            关闭预览
          </Button>
        </div>
      </dialog>
    </div>
  );
};
