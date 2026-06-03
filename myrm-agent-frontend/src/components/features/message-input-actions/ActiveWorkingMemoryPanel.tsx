'use client';

/**
 * [INPUT] useChatStore::messages/loading/workspaceDir (POS: 会话与工具进度状态);
 *   useArtifactPortalStore (POS: Artifact 门户与内容);
 *   SSE 经 messageStreamHandler 写入 progressSteps 与 FILE_DIFF 附加的 diff。
 * [OUTPUT] 活动工作记忆筹码；有 diff 时可无 workspaceDir 直接打开 Diff Artifact；无 diff 时预览走 `/files/browse/content`，可在仅有 `chatId` 时由服务端解析 workspace（无需客户端先同步 workspace_dir）。同名文件多路径合并时优先保留「更完整」的 unified diff（同时含 +/- 行优先于仅含 + 的新增片段），避免点到只剩绿色高亮的过期 diff。
 * [POS] 输入区旁的路由面板：把当前轮次工具触及的文件暴露为可预览入口。
 * E2E：筹码根节点使用 data-testid / data-filename / data-diff / data-diff-truncated；Diff 打开前通过 setCachedContent
 * 预填内容与 addTab 对齐，确保 contentLoading 为 false（避免 Skeleton 挡住 Monaco）。
 */
import React, { useMemo } from 'react';
import useChatStore from '@/store/useChatStore';
import useArtifactPortalStore, { ArtifactErrorType } from '@/store/useArtifactPortalStore';
import { FileIconSVG } from './FileIconSVG';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { useTranslations } from 'next-intl';
import type { Artifact } from '@/store/chat/types';
import { fetchWithTimeout } from '@/lib/api';

// 提取文件扩展名
const getExtension = (filename: string) => {
  const parts = filename.split('.');
  return parts.length > 1 ? parts[parts.length - 1] : 'txt';
};

// 提取文件名
const getFilename = (path: string) => {
  const parts = path.split('/');
  return parts[parts.length - 1];
};

// 剥离工作区前缀，获取相对路径
const getRelativePath = (path: string, workspaceDir: string | null) => {
  if (!workspaceDir) return path;
  if (path.startsWith(workspaceDir)) {
    const rel = path.slice(workspaceDir.length);
    return rel.startsWith('/') ? rel.slice(1) : rel;
  }
  return path;
};

/** Prefer a "richer" unified diff when the same basename appears under multiple paths (relative vs absolute). */
function scoreUnifiedDiff(diff: string): number {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
  }
  let score = 0;
  if (hasMinus && hasPlus) score += 100;
  else if (hasMinus || hasPlus) score += 10;
  if (diff.includes('@@')) score += 5;
  score += Math.min(diff.length, 500_000) / 50_000;
  return score;
}

function diffHasMinusAndPlusLines(diff: string): boolean {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
    if (hasMinus && hasPlus) return true;
  }
  return false;
}

function pickBetterDiffSnapshot(
  left: { diff?: string; diff_truncated?: boolean; path: string },
  right: { diff?: string; diff_truncated?: boolean; path: string },
): { diff?: string; diff_truncated?: boolean; path: string } {
  if (!left.diff) {
    return { diff: right.diff, diff_truncated: right.diff_truncated, path: right.path };
  }
  if (!right.diff) {
    return { diff: left.diff, diff_truncated: left.diff_truncated, path: left.path };
  }
  const sl = scoreUnifiedDiff(left.diff);
  const sr = scoreUnifiedDiff(right.diff);
  if (sr > sl) {
    return { diff: right.diff, diff_truncated: right.diff_truncated, path: right.path };
  }
  if (sl > sr) {
    return { diff: left.diff, diff_truncated: left.diff_truncated, path: left.path };
  }
  const lm = diffHasMinusAndPlusLines(left.diff);
  const rm = diffHasMinusAndPlusLines(right.diff);
  if (lm && !rm) {
    return { diff: left.diff, diff_truncated: left.diff_truncated, path: left.path };
  }
  if (rm && !lm) {
    return { diff: right.diff, diff_truncated: right.diff_truncated, path: right.path };
  }
  return left.diff.length >= right.diff.length
    ? { diff: left.diff, diff_truncated: left.diff_truncated, path: left.path }
    : { diff: right.diff, diff_truncated: right.diff_truncated, path: right.path };
}

interface ActiveFile {
  path: string;
  relativePath: string;
  filename: string;
  extension: string;
  action: string;
  lineRange?: string;
  sizeBytes?: number;
  diff?: string; // 差异内容
  diff_truncated?: boolean;
}
// 格式化文件大小
const formatBytes = (bytes?: number) => {
  if (bytes === undefined || bytes === null) return '';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

export default function ActiveWorkingMemoryPanel() {
  const t = useTranslations('chat.workingMemory');
  const messages = useChatStore((s) => s.messages);
  const isGenerating = useChatStore((s) => s.loading);
  const workspaceDir = useChatStore((s) => s.workspaceDir);
  const chatId = useChatStore((s) => s.chatId);
  const setWorkspaceDirStore = useChatStore((s) => s.setWorkspaceDir);

  const openArtifact = useArtifactPortalStore((s) => s.openArtifact);
  const setCachedContent = useArtifactPortalStore((s) => s.setCachedContent);
  const setContent = useArtifactPortalStore((s) => s.setContent);
  const setContentLoading = useArtifactPortalStore((s) => s.setContentLoading);
  const setError = useArtifactPortalStore((s) => s.setError);

  // 只在生成中，或者最后一条消息是 assistant 时显示
  const lastMessage = messages[messages.length - 1];
  const shouldShow = lastMessage?.role === 'assistant';

  const activeFiles = useMemo(() => {
    if (!shouldShow || !lastMessage?.progressSteps) return [];

    const fileMap = new Map<string, ActiveFile>();

    // 遍历当前消息的进度步骤，提取工具调用中的文件操作
    lastMessage.progressSteps.forEach((step) => {
      if (Array.isArray(step.items)) {
        step.items.forEach((item: unknown) => {
          if (item && typeof item === 'object' && 'file_path' in item) {
            const typedItem = item as {
              file_path: string;
              line_range?: string;
              action_type?: string;
              size_bytes?: string;
              diff?: string;
              diff_truncated?: boolean;
            };
            const path = typedItem.file_path;

            // 记录操作类型 (优先使用后端传来的 action_type)
            let action = typedItem.action_type || 'reading';
            // 兼容旧的或未提供 action_type 的情况
            if (!typedItem.action_type) {
              if (step.tool_name === 'write_file' || step.tool_name === 'str_replace') {
                action = 'write';
              } else if (step.tool_name === 'list_files' || step.tool_name === 'glob') {
                action = 'search';
              } else {
                action = 'read';
              }
            }

            const existing = fileMap.get(path);
            if (!existing || action === 'write') {
              fileMap.set(path, {
                path,
                relativePath: getRelativePath(path, workspaceDir),
                filename: getFilename(path),
                extension: getExtension(path),
                action,
                lineRange: typedItem.line_range,
                sizeBytes: typedItem.size_bytes ? parseInt(typedItem.size_bytes, 10) : undefined,
                diff: typedItem.diff ?? existing?.diff,
                diff_truncated: typedItem.diff ? Boolean(typedItem.diff_truncated) : existing?.diff_truncated,
              });
            } else {
              // Update line range if reading again
              if (typedItem.line_range) existing.lineRange = typedItem.line_range;
              if (typedItem.diff) {
                existing.diff = typedItem.diff;
                existing.diff_truncated = Boolean(typedItem.diff_truncated);
              }
            }
          }
        });
      }
    });

    // TASKS_STEPS 的 file_path 与 FILE_DIFF 合成行的 path 可能分别是相对路径与绝对路径，
    // 按完整 path 聚集会得到多个筹码且 data-filename 相同；Playwright/用户可能点到无 diff 的项，
    // 在无 workspaceDir 时点击无效。按 basename 合并并保留任意一侧的 diff 与优先路径。
    const mergedByFilename = new Map<string, ActiveFile>();
    for (const file of fileMap.values()) {
      const prev = mergedByFilename.get(file.filename);
      if (!prev) {
        mergedByFilename.set(file.filename, { ...file });
        continue;
      }
      const picked = pickBetterDiffSnapshot(
        {
          diff: prev.diff,
          diff_truncated: prev.diff_truncated,
          path: prev.path,
        },
        {
          diff: file.diff,
          diff_truncated: file.diff_truncated,
          path: file.path,
        },
      );
      const pathForArtifact = picked.path;
      mergedByFilename.set(file.filename, {
        path: pathForArtifact,
        relativePath: getRelativePath(pathForArtifact, workspaceDir),
        filename: file.filename,
        extension: getExtension(pathForArtifact),
        action: file.action === 'write' || prev.action === 'write' ? 'write' : file.action,
        lineRange: file.lineRange || prev.lineRange,
        sizeBytes: file.sizeBytes ?? prev.sizeBytes,
        diff: picked.diff,
        diff_truncated: Boolean(picked.diff_truncated),
      });
    }

    return Array.from(mergedByFilename.values());
  }, [lastMessage, shouldShow, workspaceDir]);

  // 智能截断：最多显示 5 个，超过则显示 "+N 更多"
  const MAX_VISIBLE = 5;
  const visibleFiles = activeFiles.slice(0, MAX_VISIBLE);
  const hiddenCount = activeFiles.length - MAX_VISIBLE;

  const handleChipClick = async (file: ActiveFile) => {
    // 如果存在 diff，则直接展示 Diff 视图（不依赖 workspaceDir：路径已在 FILE_DIFF/progressSteps 中）
    if (file.diff) {
      const diffArtifactId = `mem-diff-${file.path}`;
      const diffArtifact: Artifact = {
        id: diffArtifactId,
        filename: `${file.filename} (Diff)`,
        type: 'code',
        content_type: 'text/plain',
        size: file.diff.length,
        preview_url: '',
        download_url: '',
        language: 'diff',
      };
      setCachedContent(diffArtifactId, file.diff);
      openArtifact(diffArtifact, file.diff_truncated ? { diffPreviewTruncated: true } : undefined);
      return;
    }

    let dir = workspaceDir;
    if (!dir && chatId) {
      try {
        const { getChatDetail } = await import('@/services/chat');
        const detail = await getChatDetail(chatId, true);
        const w = detail.chat.workspace_dir;
        if (typeof w === 'string' && w.trim().length > 0) {
          dir = w.trim();
          setWorkspaceDirStore(dir);
        }
      } catch {
        /* non-fatal: /files/browse/content can still resolve workspace via chat_id */
      }
    }
    if (!dir && !chatId) return;

    const artifactId = `mem-${file.path}`;
    const artifact: Artifact = {
      id: artifactId,
      filename: file.filename,
      type: 'code',
      content_type: 'text/plain',
      size: file.sizeBytes || 0,
      preview_url: '',
      download_url: '',
      language: file.extension,
    };

    openArtifact(artifact, { lineRange: file.lineRange });
    setContentLoading(true);

    try {
      const qp = new URLSearchParams();
      qp.set('path', file.path);
      if (dir) {
        qp.set('workspace', dir);
      }
      if (chatId) {
        qp.set('chat_id', chatId);
      }
      const res = await fetchWithTimeout(`/files/browse/content?${qp.toString()}`);
      if (!res.ok) {
        if (res.status === 404) {
          // 处理幽灵文件 (Ghost File)
          setContent(`// 👻 ${t('ghostFile', { defaultMessage: 'This file was deleted or moved by the AI.' })}`);
          return;
        }
        throw new Error(`Failed to fetch content: ${res.status}`);
      }

      const isTruncated = res.headers.get('X-Content-Truncated') === 'true';
      let content = await res.text();

      if (isTruncated) {
        content =
          `/* [Warning] ${t('fileTooLarge', { defaultMessage: 'File is too large, showing the first 1MB.' })} */\n\n` +
          content;
      }

      setContent(content);
    } catch (err) {
      setError({
        type: ArtifactErrorType.Unknown,
        messageKey: 'errors.unknown',
        details: err instanceof Error ? err.message : 'Unknown error',
        retryable: false,
      });
    } finally {
      setContentLoading(false);
    }
  };

  if (!shouldShow || activeFiles.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col w-full mb-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex items-center gap-2 px-1 mb-1.5">
        {/* 呼吸灯圆点 */}
        <span className="relative flex h-2 w-2">
          {isGenerating && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
          )}
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${isGenerating ? 'bg-indigo-500' : 'bg-slate-400 dark:bg-slate-600'}`}
          ></span>
        </span>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          {t('title', { defaultMessage: 'Active Working Memory' })}
        </span>
      </div>

      <div className="flex flex-wrap gap-2 overflow-x-auto pb-1 scrollbar-hide">
        <TooltipProvider delayDuration={200}>
          {visibleFiles.map((file, index) => (
            <Tooltip key={`${file.path}-${index}`}>
              <TooltipTrigger asChild>
                <div
                  onClick={() => handleChipClick(file)}
                  data-testid="working-memory-chip"
                  data-filename={file.filename}
                  data-diff={file.diff ? '1' : '0'}
                  data-diff-truncated={file.diff_truncated ? '1' : '0'}
                  className="group flex items-center gap-2 px-2.5 py-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg hover:shadow-md hover:border-indigo-300 dark:hover:border-indigo-700 transition-all duration-200 cursor-pointer shrink-0"
                >
                  <FileIconSVG extension={file.extension} className="w-4 h-4" />
                  <span className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate max-w-[150px]">
                    {file.filename}
                  </span>
                  {/* 操作状态指示器 */}
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      file.action === 'write'
                        ? 'bg-orange-400'
                        : file.action === 'search'
                          ? 'bg-purple-400'
                          : 'bg-emerald-400'
                    }`}
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                className="max-w-[300px] break-all bg-slate-900 text-slate-50 border-slate-800"
              >
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-mono text-slate-300">
                    {file.relativePath}
                    {file.lineRange && <span className="text-indigo-400 ml-1">(Lines: {file.lineRange})</span>}
                  </span>
                  <span className="text-xs font-medium text-indigo-300">
                    {file.action === 'write'
                      ? t('action.modifying', { defaultMessage: 'AI is modifying this file' })
                      : file.action === 'search'
                        ? t('action.scanning', { defaultMessage: 'AI is scanning this directory/file' })
                        : t('action.reading', { defaultMessage: 'AI is reading this file' })}
                  </span>
                  <span className="text-[10px] text-slate-400 mt-1">
                    {file.sizeBytes !== undefined ? `${formatBytes(file.sizeBytes)} • ` : ''}
                    Click to preview in Artifacts
                  </span>
                </div>
              </TooltipContent>
            </Tooltip>
          ))}

          {hiddenCount > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 rounded-lg text-xs font-medium text-slate-500 dark:text-slate-400 cursor-default shrink-0">
                  +{hiddenCount} {t('more', { defaultMessage: 'more' })}
                </div>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[300px] bg-slate-900 text-slate-50 border-slate-800">
                <div className="flex flex-col gap-1 max-h-[200px] overflow-y-auto scrollbar-hide">
                  {activeFiles.slice(MAX_VISIBLE).map((file, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 text-xs py-1 border-b border-slate-800 last:border-0"
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          file.action === 'write'
                            ? 'bg-orange-400'
                            : file.action === 'search'
                              ? 'bg-purple-400'
                              : 'bg-emerald-400'
                        }`}
                      />
                      <span className="font-mono text-slate-300 truncate">{file.relativePath}</span>
                    </div>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          )}
        </TooltipProvider>
      </div>
    </div>
  );
}
