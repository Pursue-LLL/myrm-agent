import React, { useEffect, useState } from 'react';
import { Check, Copy, FileText, X } from 'lucide-react';
import { useWorkspaceScaffoldingStore } from './useWorkspaceScaffoldingStore';

interface ScaffoldingDocPreviewModalProps {
  className?: string;
}

export const ScaffoldingDocPreviewModal: React.FC<
  ScaffoldingDocPreviewModalProps
> = ({ className = '' }) => {
  const isOpen = useWorkspaceScaffoldingStore(
    (state) => state.isPreviewModalOpen,
  );
  const doc = useWorkspaceScaffoldingStore((state) => state.previewingDoc);
  const closePreview = useWorkspaceScaffoldingStore(
    (state) => state.closeDocPreview,
  );

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        closePreview();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, closePreview]);

  if (!isOpen || !doc) {
    return null;
  }

  const handleCopy = () => {
    void navigator.clipboard.writeText(doc.draftContent);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 1500);
  };

  return (
    <dialog
      open
      aria-label="工作区拟生成规约文档草案预览"
      className="fixed inset-0 z-50 m-0 flex h-full w-full items-center justify-center border-0 bg-background/80 p-4 backdrop-blur-md"
    >
      <div
        data-testid="scaffolding-doc-preview-modal"
        className={`flex max-h-[85vh] w-full max-w-xl flex-col rounded-2xl border border-border bg-background p-5 shadow-2xl ${className}`}
      >
        {/* 头部标题 */}
        <div className="flex items-center justify-between border-b border-border/50 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FileText className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {doc.title}
              </h3>
              <p className="text-xs text-muted-foreground">{doc.purpose}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={closePreview}
            aria-label="关闭预览"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 路径与复制操作 */}
        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-mono text-[11px] truncate">{doc.path}</span>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 rounded px-2 py-1 hover:bg-muted hover:text-foreground"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-emerald-500" />
                <span className="text-emerald-500">已复制</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                <span>复制草稿</span>
              </>
            )}
          </button>
        </div>

        {/* 预览代码与纯文本内容 */}
        <pre className="mt-2 flex-1 overflow-auto rounded-xl border border-border/60 bg-muted/20 p-4 font-mono text-xs text-foreground/90 whitespace-pre-wrap">
          {doc.draftContent}
        </pre>

        {/* 底部关闭按钮 */}
        <div className="mt-4 flex justify-end border-t border-border/40 pt-3">
          <button
            type="button"
            onClick={closePreview}
            className="rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
          >
            关闭预览
          </button>
        </div>
      </div>
    </dialog>
  );
};
