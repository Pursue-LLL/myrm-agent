'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronRight, ChevronDown, Folder, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { IconLoader } from '@/components/features/icons/PremiumIcons';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { Textarea } from '@/components/primitives/textarea';
import { cn } from '@/lib/utils/classnameUtils';
import { wikiService, type TreeNode } from '@/services/wikiService';
import { getWikiOperationErrorMessage } from './wikiTreeUtils';

interface WikiRawSourceTreeProps {
  treeData: TreeNode[];
  isLoading: boolean;
  agentScopeId?: string | null;
  highlightPath?: string | null;
  onRawDeleted?: () => void;
}

function IngestStatusDot({ status }: { status: TreeNode['ingest_status'] }) {
  const t = useTranslations('settings.wiki.concepts');

  if (status === 'tracked-modified') {
    return (
      <span
        className="h-2 w-2 shrink-0 rounded-full bg-amber-500 dark:bg-amber-400"
        title={t('rawIngestModified')}
        aria-label={t('rawIngestModified')}
      />
    );
  }
  if (status === 'tracked-clean') {
    return (
      <span
        className="h-2 w-2 shrink-0 rounded-full bg-emerald-500 dark:bg-emerald-400"
        title={t('rawIngestClean')}
        aria-label={t('rawIngestClean')}
      />
    );
  }
  return (
    <span
      className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/40"
      title={t('rawIngestNotCompiled')}
      aria-label={t('rawIngestNotCompiled')}
    />
  );
}

function nodePathMatches(node: TreeNode, targetPath: string): boolean {
  if (node.is_dir) {
    return (node.children ?? []).some((child) => nodePathMatches(child, targetPath));
  }
  const displayPath = node.id.endsWith('.md') ? node.id : `${node.id}.md`;
  return displayPath === targetPath || node.id === targetPath;
}

function RawTreeNode({
  node,
  depth,
  highlightPath,
  onRequestForget,
}: {
  node: TreeNode;
  depth: number;
  highlightPath?: string | null;
  onRequestForget: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const t = useTranslations('settings.wiki.concepts');
  const normalizedHighlight = highlightPath?.replace(/^\//, '') ?? null;

  if (node.is_dir) {
    const childMatches = normalizedHighlight
      ? (node.children ?? []).some((child) => nodePathMatches(child, normalizedHighlight))
      : false;
    const shouldOpen = open || childMatches;
    return (
      <div>
        <button
          type="button"
          className="flex w-full items-center gap-2 px-2 py-1 text-left text-sm hover:bg-muted/50"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => setOpen((value) => !value)}
        >
          {shouldOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <Folder className="h-4 w-4 shrink-0 text-primary" />
          {node.ingest_status && <IngestStatusDot status={node.ingest_status} />}
          <span className="truncate font-medium">{node.name}</span>
        </button>
        {shouldOpen &&
          (node.children ?? []).map((child) => (
            <RawTreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              highlightPath={highlightPath}
              onRequestForget={onRequestForget}
            />
          ))}
      </div>
    );
  }

  const displayPath = node.id.endsWith('.md') ? node.id : `${node.id}.md`;
  const isHighlighted =
    normalizedHighlight !== null &&
    (displayPath === normalizedHighlight || node.id === normalizedHighlight);

  return (
    <div
      data-raw-path={displayPath}
      className={cn(
        'group flex items-center gap-2 px-2 py-1 text-sm text-muted-foreground hover:bg-muted/40',
        isHighlighted && 'bg-primary/10 ring-1 ring-primary/40',
      )}
      style={{ paddingLeft: `${depth * 12 + 28}px` }}
    >
      <FileText className="h-4 w-4 shrink-0" />
      <IngestStatusDot status={node.ingest_status} />
      <span className="min-w-0 flex-1 truncate font-mono text-xs">{displayPath}</span>
      <button
        type="button"
        className="shrink-0 rounded px-2 py-0.5 text-xs text-destructive opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100"
        onClick={() => onRequestForget(displayPath)}
        aria-label={t('rawForgetConfirm')}
      >
        {t('rawForgetConfirm')}
      </button>
    </div>
  );
}

export function WikiRawSourceTree({
  treeData,
  isLoading,
  agentScopeId,
  highlightPath,
  onRawDeleted,
}: WikiRawSourceTreeProps) {
  const t = useTranslations('settings.wiki.concepts');
  const [forgetPath, setForgetPath] = useState<string | null>(null);
  const [forgetReason, setForgetReason] = useState('');
  const [isForgetting, setIsForgetting] = useState(false);

  useEffect(() => {
    if (!highlightPath) {return;}
    const normalized = highlightPath.replace(/^\//, '');
    const target = document.querySelector(`[data-raw-path="${normalized}"]`);
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [highlightPath, treeData]);

  if (isLoading) {
    return (
      <div className="flex justify-center py-6">
        <IconLoader className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (treeData.length === 0) {
    return <p className="py-4 text-center text-sm text-muted-foreground">{t('rawSourcesEmpty')}</p>;
  }

  const handleForget = async () => {
    if (!forgetPath || !forgetReason.trim()) {return;}
    setIsForgetting(true);
    try {
      await wikiService.deleteRawSource(forgetPath, forgetReason.trim(), agentScopeId);
      toast.success(t('rawForgetSuccess'));
      setForgetPath(null);
      setForgetReason('');
      onRawDeleted?.();
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('rawForgetFailed')));
    } finally {
      setIsForgetting(false);
    }
  };

  return (
    <>
      <div className={cn('max-h-48 overflow-y-auto rounded-lg border border-border/60 bg-muted/10')}>
        {treeData.map((node) => (
          <RawTreeNode
            key={node.id}
            node={node}
            depth={0}
            highlightPath={highlightPath}
            onRequestForget={setForgetPath}
          />
        ))}
      </div>
      <AlertDialog open={forgetPath !== null} onOpenChange={(open) => !open && setForgetPath(null)}>
        <AlertDialogContent className="w-[calc(100vw-2rem)] max-w-[480px]">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('rawForgetTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('rawForgetDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <p className="truncate font-mono text-xs text-muted-foreground">{forgetPath}</p>
            <label htmlFor="wiki-raw-forget-reason" className="text-sm font-medium text-foreground">
              {t('rawForgetReasonLabel')}
            </label>
            <Textarea
              id="wiki-raw-forget-reason"
              value={forgetReason}
              onChange={(event) => setForgetReason(event.target.value)}
              placeholder={t('rawForgetReasonPlaceholder')}
              rows={3}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isForgetting} />
            <AlertDialogAction disabled={!forgetReason.trim() || isForgetting} onClick={handleForget}>
              {t('rawForgetConfirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
