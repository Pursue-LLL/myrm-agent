/**
 * 交互式 UI 展示组件
 *
 * 在消息中展示 Agent 生成的交互式 UI。
 * 支持多个 UI 工件，并处理用户动作回传。
 * 包含 Toast 反馈功能。
 */

'use client';

import React, { useState } from 'react';
import { Check, Loader2 } from 'lucide-react';
import { UIArtifact, UIAction, UIActionEvent } from '@/store/chat/types';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { InteractiveUIRenderer } from './InteractiveUIRenderer';
import { toast } from '@/lib/utils/toast';

// 渐入动画样式
const fadeInAnimation = 'animate-in fade-in-0 slide-in-from-bottom-4 duration-500';
const staggerDelay = (index: number) => ({ animationDelay: `${index * 100}ms` });

interface InteractiveUIDisplayProps {
  uiArtifacts: UIArtifact[];
  onAction?: (event: UIActionEvent) => void;
  className?: string;
}

export const InteractiveUIDisplay: React.FC<InteractiveUIDisplayProps> = ({ uiArtifacts, onAction, className }) => {
  const t = useTranslations('interactiveUI');

  // 跟踪哪些 surface 已提交
  const [submittedSurfaces, setSubmittedSurfaces] = useState<Set<string>>(new Set());
  const [submittingSurfaces, setSubmittingSurfaces] = useState<Set<string>>(new Set());

  if (!uiArtifacts || uiArtifacts.length === 0) {
    return null;
  }

  const handleAction = (surfaceId: string, action: UIAction, data: Record<string, unknown>) => {
    // 构建动作事件
    const event: UIActionEvent = {
      surface_id: surfaceId,
      action_id: action.id,
      action_type: action.type,
      data,
      payload: action.payload,
    };

    if (action.type === 'submit') {
      setSubmittingSurfaces((prev) => new Set(prev).add(surfaceId));
    } else if (action.type === 'cancel') {
      toast.info(t('toast.cancelled'));
    }

    if (onAction) {
      onAction(event);
    }

    if (action.type === 'submit') {
      setSubmittingSurfaces((prev) => {
        const next = new Set(prev);
        next.delete(surfaceId);
        return next;
      });
      setSubmittedSurfaces((prev) => new Set(prev).add(surfaceId));
      toast.success(t('toast.submitSuccess'), {
        description: t('toast.submitSuccessDesc'),
      });
    }
  };

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {/* UI 工件列表 — 使用 artifact.title 作为用户可见标题，不展示泛化技术标签 */}
      <div className="flex flex-col gap-4">
        {uiArtifacts.map((artifact, index) => {
          const isSubmitted = submittedSurfaces.has(artifact.surface_id);
          const isSubmitting = submittingSurfaces.has(artifact.surface_id);

          return (
            <div
              key={artifact.surface_id}
              className={cn(
                'rounded-xl border overflow-hidden',
                'border-gray-200/80 dark:border-gray-700/80',
                'bg-gradient-to-br from-gray-50/50 to-white dark:from-gray-800/50 dark:to-gray-900',
                '',
                // 渲染动画
                fadeInAnimation,
                // 状态过渡
                'transition-all duration-300 ease-out',
                isSubmitted && 'opacity-60 scale-[0.98]',
                isSubmitting && 'ring-2 ring-blue-500/30 ring-offset-1',
              )}
              style={staggerDelay(index)}
            >
              {/* 标题栏 */}
              {artifact.title && (
                <div className="px-4 py-2.5 border-b border-gray-200/80 dark:border-gray-700/80 bg-gray-50/80 dark:bg-gray-800/80 flex items-center justify-between">
                  <h4 className="text-sm font-medium text-gray-800 dark:text-gray-200">{artifact.title}</h4>
                  {isSubmitted && (
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                      <Check className="w-3.5 h-3.5" />
                      {t('submitted')}
                    </span>
                  )}
                  {isSubmitting && (
                    <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      {t('submitting')}
                    </span>
                  )}
                </div>
              )}

              {/* UI 内容 */}
              <div className={cn('p-4', isSubmitted && 'pointer-events-none')}>
                <InteractiveUIRenderer
                  artifact={artifact}
                  onAction={(action, data) => handleAction(artifact.surface_id, action, data)}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
