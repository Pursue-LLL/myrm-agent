/**
 * 增强的加载状态组件
 * 提供更好的用户反馈和视觉效果
 */

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Loader2, FileCode, Image, FileText } from 'lucide-react';

interface LoadingStateProps {
  /** 加载类型 */
  type?: 'content' | 'artifact' | 'render';
  /** 加载消息 */
  message?: string;
  /** 文件类型（用于显示对应图标） */
  fileType?: 'code' | 'image' | 'document' | 'html';
  /** 是否显示进度条 */
  showProgress?: boolean;
  /** 进度百分比 (0-100) */
  progress?: number;
  /** 自定义类名 */
  className?: string;
}

const getFileIcon = (type?: string) => {
  switch (type) {
    case 'code':
    case 'html':
      return FileCode;
    case 'image':
      return Image;
    case 'document':
      return FileText;
    default:
      return FileCode;
  }
};

/**
 * 优化的加载状态组件
 *
 * 特点：
 * - 平滑的动画效果
 * - 可选的进度显示
 * - 根据文件类型显示对应图标
 * - 响应式设计
 */
export const LoadingState: React.FC<LoadingStateProps> = ({
  type = 'content',
  message,
  fileType,
  showProgress = false,
  progress = 0,
  className,
}) => {
  const Icon = getFileIcon(fileType);

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center h-full min-h-[200px] p-8',
        'bg-gradient-to-br from-background to-muted/20',
        className,
      )}
    >
      {/* 图标和加载动画 */}
      <div className="relative mb-4">
        {/* 背景脉冲圆 */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-20 h-20 rounded-full bg-primary/10 animate-ping" />
        </div>

        {/* 主图标 */}
        <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-primary/10">
          {fileType ? (
            <Icon className="w-8 h-8 text-primary animate-pulse" />
          ) : (
            <Loader2 className="w-8 h-8 text-primary animate-spin" />
          )}
        </div>
      </div>

      {/* 加载消息 */}
      {message && <p className="text-sm text-muted-foreground mb-2 animate-pulse">{message}</p>}

      {/* 进度条 */}
      {showProgress && (
        <div className="w-full max-w-xs mt-4">
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300 ease-out rounded-full"
              style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
            />
          </div>
          <p className="text-xs text-center text-muted-foreground mt-2">{Math.round(progress)}%</p>
        </div>
      )}

      {/* 骨架屏（可选） */}
      {type === 'render' && (
        <div className="w-full max-w-md mt-6 space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex gap-3 animate-pulse">
              <div className="w-8 h-4 rounded bg-muted" />
              <div
                className="h-4 rounded bg-muted"
                style={{
                  width: `${Math.random() * 40 + 40}%`,
                  animationDelay: `${i * 100}ms`,
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

LoadingState.displayName = 'LoadingState';

export default LoadingState;
