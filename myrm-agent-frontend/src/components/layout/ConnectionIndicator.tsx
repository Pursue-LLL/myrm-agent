'use client';

/**
 * 用户态交互式连接恢复指示器 (ConnectionIndicator)。
 *
 * 汲取 DeepSeek Harness 2026-08-28 `web-connection-recovery-control` 核心生产实践：
 * 1. 健康连接（connected 且未经历最近故障）完全不渲染，保持界面极致清爽与零视觉干扰；
 * 2. 连接断开 (disconnected) 呈现浅黄色“连接异常”，鼠标悬浮或聚焦文字变为“立即重连”按钮；
 * 3. 正在重试 (connecting) 呈现浅黄色 500ms 逐点呼吸动画，悬浮聚焦同样支持点击“立即重连”；
 * 4. 恢复连接后以浅绿色呈现“连接成功”，在界面驻留 2 秒后平滑隐去。
 */

import React, { useEffect, useRef, useState } from 'react';
import { ConnectionController, ConnectionStatus } from '@/lib/connection/connection-controller';

export interface ConnectionIndicatorProps {
  className?: string;
  controller?: ConnectionController;
}

export const ConnectionIndicator: React.FC<ConnectionIndicatorProps> = ({
  className = '',
  controller,
}) => {
  const activeController = controller ?? ConnectionController.getInstance();
  const [status, setStatus] = useState<ConnectionStatus>(activeController.status);
  const [isHovered, setIsHovered] = useState<boolean>(false);
  const [showRecoveredBadge, setShowRecoveredBadge] = useState<boolean>(false);
  const prevStatusRef = useRef<ConnectionStatus>(activeController.status);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsubscribe = activeController.subscribe((newStatus) => {
      const prevStatus = prevStatusRef.current;
      prevStatusRef.current = newStatus;

      setStatus(newStatus);

      // 如果是从 disconnected/connecting 恢复到 connected，触发 2 秒驻留展示
      if (
        newStatus === 'connected' &&
        (prevStatus === 'disconnected' || prevStatus === 'connecting')
      ) {
        setShowRecoveredBadge(true);
        if (dismissTimerRef.current) {
          clearTimeout(dismissTimerRef.current);
        }
        dismissTimerRef.current = setTimeout(() => {
          setShowRecoveredBadge(false);
          dismissTimerRef.current = null;
        }, 2000);
      } else if (newStatus !== 'connected') {
        setShowRecoveredBadge(false);
        if (dismissTimerRef.current) {
          clearTimeout(dismissTimerRef.current);
          dismissTimerRef.current = null;
        }
      }
    });

    return () => {
      unsubscribe();
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current);
      }
    };
  }, [activeController]);

  const handleReconnectClick = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    activeController.reconnectNow();
  };

  // 1. 健康且未刚恢复，完全不渲染
  if (status === 'connected' && !showRecoveredBadge) {
    return null;
  }

  // 2. 刚恢复成功态：浅绿徽章，驻留 2s
  if (status === 'connected' && showRecoveredBadge) {
    return (
      <div
        role="status"
        aria-live="polite"
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 transition-all duration-300 animate-in fade-in zoom-in-95 ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
        <span>连接成功</span>
      </div>
    );
  }

  // 3. 断开或重试中态：浅黄色操作指示器
  const isConnecting = status === 'connecting';
  const labelText = isHovered
    ? '立即重连'
    : isConnecting
    ? '正在重连'
    : '连接异常';

  return (
    <button
      type="button"
      onClick={handleReconnectClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
      title="点击立即重试连接"
      aria-label={labelText}
      className={`inline-flex items-center gap-2 px-3 py-1 text-xs font-medium rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 hover:border-amber-500/50 cursor-pointer select-none transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-amber-500/50 active:scale-95 ${className}`}
    >
      {/* 状态动效指示点 */}
      <span className="relative flex h-2 w-2">
        {isConnecting && (
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            isConnecting ? 'bg-amber-500' : 'bg-amber-600 dark:bg-amber-400'
          }`}
        />
      </span>

      <span>{labelText}</span>

      {/* 呼吸点动效 */}
      {isConnecting && !isHovered && (
        <span className="inline-flex gap-0.5 tracking-tighter">
          <span className="animate-bounce [animation-delay:-0.3s]">.</span>
          <span className="animate-bounce [animation-delay:-0.15s]">.</span>
          <span className="animate-bounce">.</span>
        </span>
      )}
    </button>
  );
};
