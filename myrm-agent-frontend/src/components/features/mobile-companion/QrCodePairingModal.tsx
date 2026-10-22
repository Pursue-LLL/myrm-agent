import React, { useState } from 'react';
import {
  X,
  QrCode,
  Copy,
  Check,
  Smartphone,
  ShieldCheck,
  Clock,
} from 'lucide-react';
import { useMobileCompanionStore } from './useMobileCompanionStore';

export interface QrCodePairingModalProps {
  onClose?: () => void;
  className?: string;
}

export const QrCodePairingModal: React.FC<QrCodePairingModalProps> = ({
  onClose,
  className = '',
}) => {
  const { isPairingModalOpen, pairingConfig, closePairingModal } =
    useMobileCompanionStore();

  const [copied, setCopied] = useState(false);

  if (!isPairingModalOpen || !pairingConfig) {
    return null;
  }

  const handleClose = () => {
    closePairingModal();
    if (onClose) {
      onClose();
    }
  };

  const handleCopy = () => {
    if (navigator.clipboard) {
      void navigator.clipboard.writeText(pairingConfig.pairingUrl);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  };

  return (
    <div
      data-testid="qr-code-pairing-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in"
    >
      <div
        className={`relative w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 shadow-2xl p-6 ${className}`}
      >
        {/* 头部标题与关闭按钮 */}
        <div className="flex items-center justify-between pb-3.5 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Smartphone className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-zinc-100">手机扫码随行带走长任务</h3>
              <p className="text-[11px] text-zinc-400">出门不用守着电脑，跨设备实时看进度与遥控</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 二维码展示区 */}
        <div className="my-5 flex flex-col items-center text-center space-y-3">
          <div className="p-4 rounded-2xl bg-white shadow-xl flex items-center justify-center">
            {/* 矢量二维码占位结构 */}
            <div className="w-48 h-48 border-4 border-zinc-900 rounded-lg p-2 flex flex-col items-center justify-center relative bg-zinc-50">
              <QrCode className="w-36 h-36 text-zinc-900" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="p-1.5 rounded-md bg-indigo-600 text-white shadow-md">
                  <Smartphone className="w-4 h-4" />
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1 text-xs text-zinc-400 font-mono">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>安全临时 Token，30 分钟内扫码有效</span>
          </div>
        </div>

        {/* 跨端直链复制 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-zinc-400">
            <span>手机浏览器直连地址:</span>
            {copied && (
              <span className="text-emerald-400 font-semibold flex items-center gap-0.5">
                <Check className="w-3 h-3" /> 已复制到剪贴板
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 p-2 rounded-lg bg-zinc-950 border border-zinc-800">
            <span className="flex-1 text-[11px] text-zinc-300 font-mono truncate">
              {pairingConfig.pairingUrl}
            </span>
            <button
              type="button"
              onClick={handleCopy}
              className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
              title="复制随行直链"
            >
              <Copy className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* PWA 说明徽标 */}
        <div className="mt-4 p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/20 text-xs text-indigo-300 space-y-1">
          <div className="flex items-center gap-1 font-semibold">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>PWA 原生级体验支持</span>
          </div>
          <p className="text-[11px] text-indigo-200/80 leading-relaxed font-sans">
            手机微信或 Safari 打开后，可点击“添加到主屏幕”，即可像独立 App 一样随时随地接收任务进度与审批推送。
          </p>
        </div>
      </div>
    </div>
  );
};
