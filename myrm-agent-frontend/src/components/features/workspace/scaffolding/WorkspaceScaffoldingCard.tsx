import React, { useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Eye,
  FileText,
  FolderTree,
  Lock,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useWorkspaceScaffoldingStore } from './useWorkspaceScaffoldingStore';
import { summarizeScaffoldingProposal } from './workspaceScaffoldingEngine';
import {
  GeneratedScaffoldDoc,
  ScaffoldingProposal,
} from './workspaceScaffoldingTypes';

interface WorkspaceScaffoldingCardProps {
  proposal: ScaffoldingProposal;
  onConfirmed?: (proposal: ScaffoldingProposal) => void;
  onCancelled?: (proposal: ScaffoldingProposal) => void;
  className?: string;
}

export const WorkspaceScaffoldingCard: React.FC<
  WorkspaceScaffoldingCardProps
> = ({ proposal, onConfirmed, onCancelled, className = '' }) => {
  const [showFileTree, setShowFileTree] = useState(false);
  const confirmProposal = useWorkspaceScaffoldingStore(
    (state) => state.confirmProposal,
  );
  const cancelProposal = useWorkspaceScaffoldingStore(
    (state) => state.cancelProposal,
  );
  const openDocPreview = useWorkspaceScaffoldingStore(
    (state) => state.openDocPreview,
  );

  const summary = summarizeScaffoldingProposal(proposal);

  const handleConfirm = () => {
    const success = confirmProposal(proposal.id);
    if (success && onConfirmed) {
      onConfirmed(proposal);
    }
  };

  const handleCancel = () => {
    const success = cancelProposal(proposal.id);
    if (success && onCancelled) {
      onCancelled(proposal);
    }
  };

  const handlePreviewDoc = (doc: GeneratedScaffoldDoc) => {
    openDocPreview(doc);
  };

  return (
    <div
      data-testid={`workspace-scaffolding-card-${proposal.id}`}
      className={`my-3 w-full max-w-xl rounded-xl border border-primary/25 bg-background/95 p-4 text-xs shadow-md backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与控制区 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FolderTree className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground text-sm">
                标准四区规整推演方案
              </span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                自然语言触发
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              工作区: {proposal.workspacePath} · 待规整文件 {proposal.moves.length} 项
            </p>
          </div>
        </div>

        {proposal.status === 'confirmed' && (
          <span className="flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>已落盘生效</span>
          </span>
        )}
        {proposal.status === 'cancelled' && (
          <span className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-[11px] font-medium text-muted-foreground">
            <X className="h-3.5 w-3.5" />
            <span>已取消规整</span>
          </span>
        )}
      </div>

      {/* 四区分区统计看板 */}
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-2">
          <div className="flex items-center gap-1.5">
            <Lock className="h-3.5 w-3.5 text-amber-500" />
            <span className="font-medium text-foreground">01 原始原件</span>
          </div>
          <span className="font-semibold text-amber-600 dark:text-amber-400">
            {summary['01_raw_materials']} 份 (只读)
          </span>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-2">
          <div className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5 text-blue-500" />
            <span className="font-medium text-foreground">02 过程草稿</span>
          </div>
          <span className="font-semibold text-blue-600 dark:text-blue-400">
            {summary['02_process_drafts']} 份
          </span>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-2">
          <div className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5 text-purple-500" />
            <span className="font-medium text-foreground">03 内容底稿</span>
          </div>
          <span className="font-semibold text-purple-600 dark:text-purple-400">
            {summary['03_content_bases']} 份
          </span>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 p-2">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            <span className="font-medium text-foreground">04 交付成果</span>
          </div>
          <span className="font-semibold text-emerald-600 dark:text-emerald-400">
            {summary['04_deliverables']} 份
          </span>
        </div>
      </div>

      {/* 预生成的项目规范草案 */}
      <div className="mt-3 rounded-lg border border-border/50 bg-background/60 p-2.5">
        <span className="font-medium text-foreground text-[11px]">
          预拟定项目双规约草案（点击预览）:
        </span>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {proposal.generatedDocs.map((doc) => (
            <button
              key={doc.path}
              type="button"
              onClick={() => {
                handlePreviewDoc(doc);
              }}
              className="flex items-center gap-1.5 rounded-md border border-border/70 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-muted/70 transition-colors"
            >
              <Eye className="h-3 w-3 text-primary" />
              <span>{doc.title.split('（')[0]}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 查看文件变动树折叠区 */}
      <div className="mt-3 border-t border-border/30 pt-2">
        <button
          type="button"
          onClick={() => {
            setShowFileTree(!showFileTree);
          }}
          className="flex w-full items-center justify-between text-[11px] text-muted-foreground hover:text-foreground"
        >
          <span>查看拟迁移文件变动树 ({proposal.moves.length} 项)</span>
          {showFileTree ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </button>

        {showFileTree && (
          <div className="mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-lg border border-border/40 bg-muted/10 p-2 font-mono text-[10px]">
            {proposal.moves.map((move) => (
              <div
                key={move.sourcePath}
                className="flex items-center justify-between gap-2 border-b border-border/20 pb-1"
              >
                <div className="flex items-center gap-1.5 truncate">
                  {move.isReadOnly && (
                    <Lock className="h-2.5 w-2.5 shrink-0 text-amber-500" />
                  )}
                  <span className="truncate">{move.fileName}</span>
                </div>
                <span className="shrink-0 text-muted-foreground">
                  ➔ {move.targetZone}/
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 底部操作与确认门禁 */}
      <div className="mt-3.5 flex items-center justify-between border-t border-border/40 pt-3 text-[11px]">
        <div className="flex items-center gap-1 text-muted-foreground">
          <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
          <span>确认前不执行任何文件物理修改</span>
        </div>

        {proposal.status === 'pending_review' ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-lg border border-border/70 px-3 py-1 font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              保持原样
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              className="flex items-center gap-1 rounded-lg bg-primary px-3 py-1 font-medium text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
            >
              <Check className="h-3 w-3" />
              <span>确认落盘 (Apply)</span>
            </button>
          </div>
        ) : (
          <span className="text-muted-foreground">操作已终态锁定</span>
        )}
      </div>
    </div>
  );
};
