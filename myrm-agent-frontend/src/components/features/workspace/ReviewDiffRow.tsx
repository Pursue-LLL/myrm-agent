'use client';

/**
 * [INPUT]
 * - ReviewPanel::ReviewFileDiff (POS: 变更审阅与会话反馈侧栏组件的数据单元)
 * - lib/diff/DiffViewer::DiffViewer (POS: lib/diff 层的共享 Diff 可视化组件)
 *
 * [OUTPUT]
 * - ReviewDiffRow: 单文件差异行（头部 + 展开详情），rawDiff 懒计算
 * - ReviewFileDiff: 单文件差异数据类型（含会话聚合的消息归属）
 * - reviewRowKey: 行稳定身份（消息序号 + 路径）
 *
 * [POS]
 * workspace 审查面板的单文件行组件。头部固定高度供虚拟化测量，
 * 展开详情由 DiffViewer 渲染。
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { FileEdit, ChevronDown, ChevronRight, Copy, Check, ChevronUp } from 'lucide-react';
import { createPatch } from 'diff';
import { cn } from '@/lib/utils/classnameUtils';
import { DiffViewer } from '@/lib/diff/DiffViewer';

export interface ReviewFileDiff {
  path: string;
  operation: string;
  original: string | null;
  current: string | null;
  isBinary: boolean;
  truncated?: boolean;
  additions?: number;
  deletions?: number;
  /** Owning message in session-aggregated lists; absent in single-message mode. */
  _msgId?: string;
}

/** Stable row identity: same path may repeat across messages in session mode. */
export function reviewRowKey(diff: ReviewFileDiff): string {
  return diff._msgId ? `${diff._msgId}::${diff.path}` : diff.path;
}

interface ReviewDiffRowProps {
  diff: ReviewFileDiff;
  rowKey: string;
  expanded: boolean;
  longExpanded: boolean;
  copied: boolean;
  onToggle: (key: string) => void;
  onToggleLong: (key: string) => void;
  onCopy: (content: string, key: string) => void;
}

const MAX_VISIBLE_DIFF_LINES = 300;

function buildRawDiff(diff: ReviewFileDiff): string {
  if (diff.isBinary || diff.truncated) {
    return '';
  }
  return createPatch(diff.path, diff.original ?? '', diff.current ?? '', '', '', { context: 3 });
}

const ReviewDiffRow: React.FC<ReviewDiffRowProps> = memo(
  ({ diff, rowKey, expanded, longExpanded, copied, onToggle, onToggleLong, onCopy }) => {
    const t = useTranslations('multiPane');
    const fileName = diff.path.split('/').pop() || diff.path;

    const rawDiff = useMemo(() => (expanded ? buildRawDiff(diff) : ''), [expanded, diff]);
    const diffLineCount = useMemo(() => (rawDiff ? rawDiff.split('\n').length : 0), [rawDiff]);
    const isLong = diffLineCount > MAX_VISIBLE_DIFF_LINES;

    return (
      <div className="border-b border-border/30">
        <div className="w-full flex items-center justify-between px-4 py-2 text-sm hover:bg-muted/50 transition-colors min-h-[40px]">
          <button
            type="button"
            onClick={() => onToggle(rowKey)}
            className="flex items-center gap-2 min-w-0 flex-1 text-left"
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span
              className={cn(
                'text-xs px-1.5 py-0.5 rounded font-mono shrink-0',
                diff.operation === 'create'
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
              )}
            >
              {diff.operation === 'create' ? 'A' : 'M'}
            </span>
            <span className="text-muted-foreground truncate">{diff.path.replace(fileName, '')}</span>
            <span className="font-medium shrink-0 truncate max-w-[140px] sm:max-w-none" title={diff.path}>
              {fileName}
            </span>
            {(diff.additions ?? 0) > 0 || (diff.deletions ?? 0) > 0 ? (
              <span className="text-[11px] font-mono text-muted-foreground shrink-0">
                +{diff.additions ?? 0}/-{diff.deletions ?? 0}
              </span>
            ) : null}
            {diff.truncated ? (
              <span className="text-[11px] text-yellow-600 dark:text-yellow-400 shrink-0">Too large</span>
            ) : null}
          </button>

          {expanded && !diff.isBinary && !diff.truncated && rawDiff && (
            <button
              type="button"
              onClick={() => onCopy(rawDiff, rowKey)}
              title={t('copyDiff')}
              aria-label={t('copyDiff')}
              className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0 ml-2"
            >
              {copied ? <Check size={13} className="text-green-500" /> : <Copy size={13} />}
            </button>
          )}
        </div>

        {expanded && diff.isBinary && (
          <div className="px-4 pb-3 text-xs text-muted-foreground italic">{t('binaryFileDiff')}</div>
        )}

        {expanded && diff.truncated && (
          <div className="px-4 pb-3 text-xs text-muted-foreground">
            File too large to preview inline. Open it in the workspace to review.
          </div>
        )}

        {expanded && !diff.isBinary && !diff.truncated && rawDiff && (
          <div className="px-4 pb-3">
            {isLong && !longExpanded ? (
              <DiffViewer
                diff={rawDiff.split('\n').slice(0, MAX_VISIBLE_DIFF_LINES).join('\n')}
                filePath={diff.path}
                embedded
              />
            ) : (
              <DiffViewer diff={rawDiff} filePath={diff.path} embedded />
            )}
            {isLong && (
              <button
                type="button"
                onClick={() => onToggleLong(rowKey)}
                className="w-full flex items-center justify-center gap-1.5 text-xs text-primary/80 hover:text-primary py-1.5 mt-1.5 rounded bg-muted/40 hover:bg-muted/70 transition-colors font-medium"
              >
                {longExpanded ? (
                  <>
                    <ChevronUp size={13} />
                    <span>{t('collapseLongDiff')}</span>
                  </>
                ) : (
                  <>
                    <ChevronDown size={13} />
                    <span>{t('expandLongDiff', { count: diffLineCount - MAX_VISIBLE_DIFF_LINES })}</span>
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {expanded && !diff.isBinary && !diff.truncated && !rawDiff && (
          <div className="px-4 pb-3 text-xs text-muted-foreground flex items-center gap-1.5">
            <FileEdit size={13} />
            No text changes.
          </div>
        )}
      </div>
    );
  },
);

ReviewDiffRow.displayName = 'ReviewDiffRow';

export default ReviewDiffRow;
