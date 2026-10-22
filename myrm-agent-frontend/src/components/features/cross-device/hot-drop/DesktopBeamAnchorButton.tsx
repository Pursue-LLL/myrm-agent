/**
 * Desktop Beam Anchor Button Component
 * 桌面端输入框附件栏微型手机直投锚点与近场扫码配对浮层
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准与键盘导航。
 */

import React, { useRef, useEffect } from 'react';
import {
  Smartphone,
  QrCode,
  RefreshCw,
  Wifi,
  Check,
  Camera,
  Zap,
} from 'lucide-react';
import { useCrossDeviceDropStore } from './useCrossDeviceDropStore';

export interface DesktopBeamAnchorButtonProps {
  className?: string;
}

export const DesktopBeamAnchorButton: React.FC<
  DesktopBeamAnchorButtonProps
> = ({ className = '' }) => {
  const popoverRef = useRef<HTMLDivElement>(null);

  const {
    activeSession,
    isAnchorPopoverOpen,
    setAnchorPopoverOpen,
    initNewSession,
    simulateCameraShootAndBeam,
  } = useCrossDeviceDropStore();

  // 点击外部收起配对弹层
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent): void => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(event.target as Node)
      ) {
        setAnchorPopoverOpen(false);
      }
    };

    if (isAnchorPopoverOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isAnchorPopoverOpen, setAnchorPopoverOpen]);

  const isConnected = activeSession.connectionState === 'connected';
  const isBeaming = activeSession.connectionState === 'beaming';

  return (
    <div
      ref={popoverRef}
      className={`relative inline-flex items-center ${className}`}
      data-testid="desktop-beam-anchor-root"
    >
      {/* 桌面端附件区常驻微型按钮 */}
      <button
        type="button"
        data-testid="desktop-beam-trigger-btn"
        onClick={() => {
          setAnchorPopoverOpen(!isAnchorPopoverOpen);
        }}
        className={`group flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-all duration-200 shadow-sm ${
          isConnected
            ? 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300 hover:bg-emerald-950/40'
            : isBeaming
            ? 'border-indigo-500/50 bg-indigo-950/30 text-indigo-300 animate-pulse'
            : 'border-neutral-800 bg-neutral-900/80 text-neutral-300 hover:border-neutral-700 hover:bg-neutral-800'
        }`}
        title="手机零摩擦拍照直投到电脑输入框"
      >
        <Smartphone className="h-3.5 w-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
        <span className="font-mono text-[11px] font-medium hidden sm:inline">
          {isConnected ? activeSession.connectedDeviceName : '手机直投'}
        </span>

        {/* 状态指示点 */}
        <span
          data-testid="beam-status-indicator"
          className={`h-1.5 w-1.5 rounded-full ${
            isConnected
              ? 'bg-emerald-400'
              : isBeaming
              ? 'bg-indigo-400 animate-ping'
              : 'bg-neutral-500'
          }`}
        />
      </button>

      {/* 动态配对码与二维码 Popover 浮层 */}
      {isAnchorPopoverOpen && (
        <div
          data-testid="beam-anchor-popover"
          className="absolute bottom-full mb-2 left-0 z-50 w-72 rounded-2xl border border-neutral-800 bg-neutral-900/95 p-4 shadow-2xl backdrop-blur-xl text-neutral-100 space-y-3"
        >
          {/* 标题栏 */}
          <div className="flex items-center justify-between border-b border-neutral-800/80 pb-2">
            <div className="flex items-center gap-1.5">
              <QrCode className="h-4 w-4 text-indigo-400" />
              <span className="font-semibold text-xs">无线相机与素材直投</span>
            </div>
            <button
              type="button"
              data-testid="refresh-pair-code-btn"
              onClick={() => {
                initNewSession();
              }}
              className="text-neutral-400 hover:text-white transition-colors p-1 rounded-md hover:bg-neutral-800"
              title="刷新配对码与会话"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* 二维码与配对码核心区 */}
          <div className="flex flex-col items-center justify-center rounded-xl bg-neutral-950/80 border border-neutral-800/80 p-3 space-y-2">
            {/* 模拟扫码区域 */}
            <div
              className="flex h-28 w-28 items-center justify-center rounded-lg border-2 border-dashed border-indigo-500/50 bg-indigo-950/20"
              data-testid="beam-qr-container"
            >
              <Camera className="h-8 w-8 text-indigo-400 animate-bounce" />
            </div>

            <div className="text-center space-y-0.5">
              <div className="text-[10px] text-neutral-400">
                任意手机扫码或输入配对码
              </div>
              <div
                data-testid="beam-pair-code-text"
                className="font-mono text-lg font-bold tracking-widest text-indigo-300"
              >
                {activeSession.pairCode}
              </div>
            </div>
          </div>

          {/* 连接模式与说明 */}
          <div className="flex items-center justify-between text-[11px] text-neutral-400 font-mono px-1">
            <span className="flex items-center gap-1">
              <Wifi className="h-3 w-3 text-emerald-400" />
              <span>{activeSession.transportMode.toUpperCase()} 局域网直连</span>
            </span>
            <span className="text-indigo-400">零云端中转</span>
          </div>

          {/* 操作辅助：测试模拟手机拍摄推流 */}
          <button
            type="button"
            data-testid="simulate-beam-btn"
            onClick={() => {
              simulateCameraShootAndBeam();
            }}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600/80 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 transition-colors"
          >
            <Zap className="h-3.5 w-3.5" />
            <span>模拟手机拍照并直投电脑光标</span>
          </button>

          {isConnected && (
            <div className="flex items-center gap-1.5 rounded-lg bg-emerald-950/30 border border-emerald-800/40 p-2 text-[11px] text-emerald-300">
              <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
              <span>
                设备已绑定：{activeSession.connectedDeviceName}，按快门即达。
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
