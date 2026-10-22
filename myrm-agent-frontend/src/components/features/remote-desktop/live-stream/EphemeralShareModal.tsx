import React, { useState } from 'react';
import {
  Share2,
  Copy,
  Check,
  Clock,
  Key,
  ShieldCheck,
  X,
  Smartphone,
  RefreshCw,
  QrCode,
} from 'lucide-react';
import { useRemoteDesktopStore } from './useRemoteDesktopStore';
import { formatTimeRemaining } from './ephemeralTokenSecurity';
import { ShareOptions } from './remoteDesktopTypes';

export const EphemeralShareModal: React.FC = () => {
  const {
    isShareModalOpen,
    currentTicket,
    closeShareModal,
    createShareTicket,
  } = useRemoteDesktopStore();

  const [copied, setCopied] = useState(false);
  const [ttl, setTtl] = useState(7200);
  const [allowTakeover, setAllowTakeover] = useState(false);
  const [oneTimeOnly, setOneTimeOnly] = useState(false);

  if (!isShareModalOpen || !currentTicket) {
    return null;
  }

  const handleCopy = async () => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      await navigator.clipboard.writeText(currentTicket.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRegenerate = () => {
    const opts: ShareOptions = {
      ttlSeconds: ttl,
      allowTakeover,
      oneTimeOnly,
    };
    createShareTicket(opts);
  };

  const ttlOptions = [
    { label: '1 小时', value: 3600 },
    { label: '2 小时', value: 7200 },
    { label: '24 小时', value: 86400 },
  ];

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="share-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="ephemeral-share-modal"
      >
        {/* 弹窗头部 */}
        <header className="px-5 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-indigo-600/30 text-indigo-400 border border-indigo-500/40">
              <Share2 className="w-4 h-4" />
            </div>
            <div>
              <h3 id="share-modal-title" className="font-bold text-sm text-white">
                免登录时效安全分享链接
              </h3>
              <p className="text-xs text-slate-400">
                支持手机端/第三方随时免密旁听监工，带加密数字签名与到期自毁
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeShareModal}
            aria-label="关闭分享窗口"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 链接展示与参数配置 */}
        <div className="p-5 space-y-4 text-xs">
          {/* 生成的时效链接框 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-slate-400">
              <span className="font-semibold text-slate-300">专属免密旁听链接</span>
              <span className="text-[11px] font-mono text-emerald-400 flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>有效期至：{formatTimeRemaining(currentTicket.expiresAt)}</span>
              </span>
            </div>
            <div className="flex items-center space-x-2 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
              <input
                type="text"
                readOnly
                value={currentTicket.url}
                className="flex-1 bg-transparent text-slate-200 text-xs font-mono focus:outline-none select-all truncate"
              />
              <button
                type="button"
                onClick={handleCopy}
                aria-label="复制时效分享链接"
                className="px-3 py-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white rounded flex items-center space-x-1.5 transition-all shrink-0"
              >
                {copied ? (
                  <>
                    <Check className="w-3.5 h-3.5 text-emerald-300" />
                    <span>已复制</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3.5 h-3.5" />
                    <span>复制</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* 选项配置：时长与权限 */}
          <div className="space-y-3 pt-2 border-t border-slate-800">
            <div>
              <span className="font-semibold text-slate-300 block mb-1.5">
                时效周期 (TTL)
              </span>
              <div className="flex items-center space-x-2">
                {ttlOptions.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTtl(opt.value)}
                    className={`px-3 py-1.5 rounded-md font-medium border text-xs transition-colors ${
                      ttl === opt.value
                        ? 'bg-indigo-600 text-white border-indigo-500'
                        : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 pt-1">
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={allowTakeover}
                  onChange={(e) => setAllowTakeover(e.target.checked)}
                  className="rounded border-slate-700 text-indigo-600 focus:ring-0"
                />
                <span className="text-slate-200">
                  允许访客双向接管远程桌面（默认仅允许单向旁听观看）
                </span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={oneTimeOnly}
                  onChange={(e) => setOneTimeOnly(e.target.checked)}
                  className="rounded border-slate-700 text-indigo-600 focus:ring-0"
                />
                <span className="text-slate-200">
                  单次访问后立即销毁凭据 (One-time Ephemeral)
                </span>
              </label>
            </div>
          </div>

          {/* 安全说明 */}
          <div className="p-3 rounded-lg bg-slate-950/50 border border-slate-800 text-[11px] text-slate-400 space-y-1">
            <div className="font-semibold text-slate-300 flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>密码学时效签名保护</span>
            </div>
            <p>
              链接由沙箱凭据网关实时签发，参数被篡改或逾期后服务端将立即切断 WebRTC 流，严防会话劫持与泄露。
            </p>
          </div>
        </div>

        {/* 底部操作区 */}
        <footer className="px-5 py-3 border-t border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <button
            type="button"
            onClick={handleRegenerate}
            aria-label="刷新并重新生成凭证"
            className="px-3 py-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded border border-slate-700 flex items-center space-x-1.5 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>重新签发链接</span>
          </button>
          <button
            type="button"
            onClick={closeShareModal}
            className="px-4 py-1.5 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition-colors"
          >
            完成
          </button>
        </footer>
      </dialog>
    </>
  );
};
