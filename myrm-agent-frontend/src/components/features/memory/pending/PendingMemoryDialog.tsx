'use client';

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  Check,
  X,
  Pencil,
  MessageSquare,
  Tag,
  ShieldCheck,
  Sparkles,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
} from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { useMemoryStore } from '@/store/memory';
import MemoryTypeIcon from '../cards/MemoryTypeIcon';
import { toast } from '@/hooks/shared/useToast';

const PendingMemoryDialog = memo(() => {
  const t = useTranslations('memory');
  const router = useRouter();
  const { currentPendingMemory, isConfirmDialogOpen, closeConfirmDialog, approveMemory, rejectMemory } =
    useMemoryStore();

  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showReasoning, setShowReasoning] = useState(true);
  const editInputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing) {
      editInputRef.current?.focus();
    }
  }, [isEditing]);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      if (!open) {
        closeConfirmDialog();
        setIsEditing(false);
        setEditedContent('');
      }
    },
    [closeConfirmDialog],
  );

  const handleStartEdit = useCallback(() => {
    if (currentPendingMemory) {
      setEditedContent(currentPendingMemory.content);
      setIsEditing(true);
    }
  }, [currentPendingMemory]);

  const handleApprove = useCallback(async () => {
    if (!currentPendingMemory) {
      return;
    }

    setIsLoading(true);
    try {
      const content = isEditing && editedContent !== currentPendingMemory.content ? editedContent : undefined;
      await approveMemory(currentPendingMemory.id, content);
      toast({
        title: t('approveSuccess'),
        description: t('approveSuccessDesc'),
      });
    } catch (error) {
      toast({
        title: t('approveFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
      setIsEditing(false);
      setEditedContent('');
    }
  }, [currentPendingMemory, isEditing, editedContent, approveMemory, t]);

  const handleReject = useCallback(async () => {
    if (!currentPendingMemory) {
      return;
    }

    setIsLoading(true);
    try {
      await rejectMemory(currentPendingMemory.id);
      toast({
        title: t('rejectSuccess'),
        description: t('rejectSuccessDesc'),
      });
    } catch (error) {
      toast({
        title: t('rejectFailed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, [currentPendingMemory, rejectMemory, t]);

  if (!currentPendingMemory) {
    return null;
  }

  const memoryType = currentPendingMemory.memory_type;

  return (
    <Dialog open={isConfirmDialogOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[480px] p-0 overflow-hidden">
        {/* 顶部装饰渐变 */}
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />

        <div className="relative p-6">
          <DialogHeader className="space-y-4">
            {/* 图标和标题 */}
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full" />
                <div className="relative bg-gradient-to-br from-primary/10 to-primary/5 p-3 rounded-2xl border border-primary/10">
                  <IconGlow className="h-6 w-6 text-primary" />
                </div>
              </div>
              <div>
                <DialogTitle className="text-xl font-semibold">{t('confirmTitle')}</DialogTitle>
                <DialogDescription className="text-sm mt-1">{t('confirmDescription')}</DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {/* 记忆内容卡片 */}
          <div className="mt-6 rounded-xl border border-border/50 bg-accent/30 overflow-hidden">
            {/* 类型标签 */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50 bg-background/50">
              <MemoryTypeIcon type={memoryType} size={16} showTooltip />
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t(`types.${memoryType}`)}
              </span>

              {/* 来源信息 */}
              {currentPendingMemory.source_chat_id && (
                <>
                  <span className="text-muted-foreground/30">•</span>
                  <button
                    onClick={() => {
                      const url = currentPendingMemory.source_message_id
                        ? `/${currentPendingMemory.source_chat_id}?highlight=${currentPendingMemory.source_message_id}`
                        : `/${currentPendingMemory.source_chat_id}`;
                      router.push(url);
                    }}
                    className="flex items-center gap-1 text-xs text-primary/70 hover:text-primary transition-colors"
                  >
                    <MessageSquare size={10} />
                    <span>{t('viewSourceChat')}</span>
                  </button>
                </>
              )}
            </div>

            {/* 结构化元数据胶囊条 */}
            <div className="flex flex-wrap items-center gap-1.5 px-4 py-2 border-b border-border/30 bg-background/30 text-[11px]">
              {/* 置信度徽章 */}
              {currentPendingMemory.confidence !== undefined && currentPendingMemory.confidence !== null && (
                (() => {
                  const percent = Math.round(currentPendingMemory.confidence * 100);
                  if (percent >= 85) {
                    return (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        <ShieldCheck size={11} />
                        <span>{percent}% {t('confidenceHigh')}</span>
                      </span>
                    );
                  }
                  if (percent >= 60) {
                    return (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                        <Sparkles size={11} />
                        <span>{percent}% {t('confidenceMedium')}</span>
                      </span>
                    );
                  }
                  return (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-muted text-muted-foreground border border-border/50">
                      <AlertCircle size={11} />
                      <span>{percent}% {t('confidenceLow')}</span>
                    </span>
                  );
                })()
              )}

              {/* 类别标签 */}
              {currentPendingMemory.kind && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-primary/10 text-primary border border-primary/20">
                  <Tag size={10} />
                  <span>{currentPendingMemory.kind}</span>
                </span>
              )}

              {/* 有效期 */}
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-accent/60 text-muted-foreground border border-border/40">
                <Clock size={10} />
                <span>
                  {currentPendingMemory.expected_valid_days
                    ? `${currentPendingMemory.expected_valid_days}d`
                    : t('validPermanent')}
                </span>
              </span>

              {/* 冲突裁决策略 */}
              {currentPendingMemory.is_conflict && (
                currentPendingMemory.conflict_auto_resolve_at ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                    <Clock size={10} />
                    <span>{t('conflict.title')}</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium bg-destructive/10 text-destructive border border-destructive/20">
                    <ShieldAlert size={10} />
                    <span>{t('manualReviewRequired')}</span>
                  </span>
                )
              )}
            </div>

            {/* 内容区域 */}
            <div className="p-4 space-y-3">
              {isEditing ? (
                <textarea
                  ref={editInputRef}
                  value={editedContent}
                  onChange={(e) => setEditedContent(e.target.value)}
                  className={cn(
                    'w-full min-h-[100px] p-3 rounded-lg resize-none',
                    'bg-background border border-border/50',
                    'text-sm text-foreground leading-relaxed',
                    'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                    'transition-all duration-200',
                  )}
                  placeholder={t('editPlaceholder')}
                />
              ) : (
                <p className="text-sm text-foreground leading-relaxed">{currentPendingMemory.content}</p>
              )}

              {/* 提取推理依据 */}
              {currentPendingMemory.influence_explanation && (
                <div className="pt-2 border-t border-border/40">
                  <button
                    type="button"
                    onClick={() => setShowReasoning(!showReasoning)}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors font-medium"
                  >
                    {showReasoning ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    <span>{t('extractionReason')}</span>
                  </button>
                  {showReasoning && (
                    <div className="mt-1.5 p-2.5 rounded-lg bg-background/60 border border-border/40 text-xs text-muted-foreground leading-relaxed">
                      {currentPendingMemory.influence_explanation}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 操作按钮 */}
          <DialogFooter className="mt-6 flex-col sm:flex-row gap-2">
            {!isEditing && (
              <button
                onClick={handleStartEdit}
                disabled={isLoading}
                className={cn(
                  'flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
                  'text-sm font-medium transition-all duration-200',
                  'border border-border/50 hover:border-border',
                  'text-muted-foreground hover:text-foreground',
                  'hover:bg-accent',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <Pencil size={14} />
                {t('edit')}
              </button>
            )}

            <div className="flex gap-2 sm:ml-auto">
              <button
                onClick={handleReject}
                disabled={isLoading}
                className={cn(
                  'flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg',
                  'text-sm font-medium transition-all duration-200',
                  'border border-destructive/30 hover:border-destructive/50',
                  'text-destructive hover:bg-destructive/5',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <X size={14} />
                {t('reject')}
              </button>

              <button
                onClick={handleApprove}
                disabled={isLoading}
                className={cn(
                  'flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg',
                  'text-sm font-medium transition-all duration-200',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90',
                  'shadow-lg shadow-primary/20',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <Check size={14} />
                {isEditing ? t('saveAndAccept') : t('accept')}
              </button>
            </div>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
});

PendingMemoryDialog.displayName = 'PendingMemoryDialog';

export default PendingMemoryDialog;
