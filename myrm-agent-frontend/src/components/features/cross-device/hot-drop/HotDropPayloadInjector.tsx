/**
 * Hot-Drop Payload Injector Component
 * 桌面端接收手机直投素材后的即时输入框悬浮挂载与光标热注入卡片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 键盘无障碍支持与平滑进出场动效。
 */

import React, { useEffect } from 'react';
import {
  Zap,
  Sparkles,
  Smartphone,
  X,
  Check,
  FileText,
} from 'lucide-react';
import { useCrossDeviceDropStore } from './useCrossDeviceDropStore';
import { formatByteSize } from './beamTransportProtocol';

export interface HotDropPayloadInjectorProps {
  className?: string;
  targetInputSelector?: string;
}

export const HotDropPayloadInjector: React.FC<HotDropPayloadInjectorProps> = ({
  className = '',
  targetInputSelector = '#chat-user-input',
}) => {
  const {
    activeIncomingPayload,
    injectPayloadToTarget,
    dismissActivePayload,
  } = useCrossDeviceDropStore();

  // 键盘快捷监听：Enter 确认注入，Escape 取消
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (!activeIncomingPayload) {
        return;
      }

      if (e.key === 'Escape') {
        dismissActivePayload();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeIncomingPayload, dismissActivePayload]);

  if (!activeIncomingPayload) {
    return null;
  }

  const handleInject = (): void => {
    injectPayloadToTarget(activeIncomingPayload.id, targetInputSelector);
  };

  return (
    <div
      data-testid="hot-drop-payload-injector"
      className={`relative flex items-center justify-between gap-3 rounded-xl border border-indigo-500/50 bg-indigo-950/40 p-3 backdrop-blur-md text-neutral-100 shadow-xl transition-all duration-300 ${className}`}
    >
      {/* 缩略图与来源信息 */}
      <div className="flex items-center gap-3 overflow-hidden">
        <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg border border-neutral-700 bg-neutral-900">
          {/* oxlint-disable-next-line next/no-img-element */}
          <img
            src={activeIncomingPayload.dataUrl}
            alt={activeIncomingPayload.fileName}
            className="h-full w-full object-cover"
            data-testid="injector-thumbnail-img"
          />
          <div className="absolute top-0 right-0 rounded-bl bg-indigo-600/90 p-0.5">
            <Zap className="h-2.5 w-2.5 text-white" />
          </div>
        </div>

        <div className="space-y-0.5 overflow-hidden">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-white truncate">
            <span className="truncate">{activeIncomingPayload.fileName}</span>
            <span className="rounded bg-indigo-500/20 px-1 py-0.2 font-mono text-[9px] text-indigo-300">
              {formatByteSize(activeIncomingPayload.fileSizeBytes)}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[10px] text-neutral-400 font-mono">
            <span className="flex items-center gap-1 text-emerald-400">
              <Smartphone className="h-3 w-3" />
              <span>{activeIncomingPayload.sourceDeviceName} 直投</span>
            </span>
          </div>

          {activeIncomingPayload.suggestedPrompt && (
            <div className="flex items-center gap-1 text-[11px] text-neutral-300 truncate">
              <Sparkles className="h-3 w-3 text-indigo-400 shrink-0" />
              <span className="truncate italic">
                “{activeIncomingPayload.suggestedPrompt}”
              </span>
            </div>
          )}

          {activeIncomingPayload.ocrExtractedText && (
            <div className="flex items-center gap-1 text-[10px] text-neutral-400 truncate font-mono">
              <FileText className="h-3 w-3 text-cyan-400 shrink-0" />
              <span className="truncate">
                OCR: {activeIncomingPayload.ocrExtractedText}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* 操作按钮区 */}
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          type="button"
          data-testid="confirm-inject-btn"
          onClick={handleInject}
          className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors shadow-sm"
        >
          <Check className="h-3.5 w-3.5" />
          <span>注入光标</span>
        </button>

        <button
          type="button"
          data-testid="dismiss-inject-btn"
          onClick={dismissActivePayload}
          className="rounded-lg p-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
          title="忽略该投送素材"
          aria-label="忽略"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
