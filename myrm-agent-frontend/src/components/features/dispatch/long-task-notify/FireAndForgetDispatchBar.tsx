import React, { useState } from 'react';
import {
  Send,
  Bell,
  Server,
  Clock,
  ShieldCheck,
  X,
  Smartphone,
  Zap,
} from 'lucide-react';
import { useLongTaskNotifyStore } from './useLongTaskNotifyStore';
import { formatTaskDuration } from './longTaskRejoinEngine';

export const FireAndForgetDispatchBar: React.FC = () => {
  const {
    isDispatchModalOpen,
    closeDispatchModal,
    dispatchTask,
  } = useLongTaskNotifyStore();

  const [title, setTitle] = useState('竞品商业定价策略与技术参数深度对比');
  const [prompt, setPrompt] = useState(
    '针对5家头部竞品，抓取其公开定价表与SLA承诺，输出带官方源链接的决策清单'
  );
  const [estDurationSec, setEstDurationSec] = useState(180);
  const [notifyWebPush, setNotifyWebPush] = useState(true);
  const [notifySystem, setNotifySystem] = useState(true);

  if (!isDispatchModalOpen) {
    return null;
  }

  const handleDispatch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      return;
    }
    dispatchTask({
      title,
      prompt,
      estimatedDurationSec: estDurationSec,
      notifyWebPush,
      notifySystem,
    });
  };

  return (
    <>
      <div
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />
      <dialog
        open
        aria-labelledby="dispatch-modal-title"
        className="fixed inset-0 z-50 m-auto w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl p-0 flex flex-col text-slate-100 overflow-hidden"
        data-testid="fire-and-forget-dispatch-modal"
      >
        {/* 头部标题与免守候声明 */}
        <header className="px-5 py-4 border-b border-slate-800 bg-slate-950/70 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-emerald-600/20 text-emerald-400 border border-emerald-500/30">
              <Zap className="w-4 h-4" />
            </div>
            <div>
              <h3 id="dispatch-modal-title" className="font-bold text-xs text-white">
                碎片时间长任务「发完走人」确认
              </h3>
              <p className="text-[10px] text-slate-400">
                云端沙箱独立常驻执行，锁屏、切后台进程不中断，完成即推送
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeDispatchModal}
            aria-label="关闭长任务派发窗口"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 表单内容区 */}
        <form onSubmit={handleDispatch} className="p-5 space-y-4 text-xs">
          {/* 任务名称 */}
          <div className="space-y-1">
            <label htmlFor="task-title-input" className="font-semibold text-slate-300 block">
              任务名称
            </label>
            <input
              id="task-title-input"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-emerald-500 font-sans"
              required
            />
          </div>

          {/* 任务指令 */}
          <div className="space-y-1">
            <label htmlFor="task-prompt-textarea" className="font-semibold text-slate-300 block">
              执行目标与提示词
            </label>
            <textarea
              id="task-prompt-textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 resize-none font-sans leading-relaxed"
            />
          </div>

          {/* 执行环境与预估耗时卡 */}
          <div className="grid grid-cols-2 gap-2.5 p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-[11px]">
            <div className="flex items-center space-x-2">
              <Server className="w-4 h-4 text-indigo-400 shrink-0" />
              <div>
                <span className="text-slate-400 block text-[10px]">执行环境</span>
                <span className="font-semibold text-slate-200">常驻云端独立沙箱</span>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-amber-400 shrink-0" />
              <div>
                <span className="text-slate-400 block text-[10px]">预估耗时</span>
                <span className="font-semibold text-slate-200">
                  约 {formatTaskDuration(estDurationSec)} (地铁到站前备好)
                </span>
              </div>
            </div>
          </div>

          {/* 完成通知通道配置 */}
          <div className="space-y-2 pt-1 border-t border-slate-800">
            <span className="font-semibold text-slate-300 block text-xs">
              免守候离线通知偏好
            </span>
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={notifyWebPush}
                onChange={(e) => setNotifyWebPush(e.target.checked)}
                className="rounded border-slate-700 text-emerald-600 focus:ring-0"
              />
              <span className="text-slate-200 flex items-center space-x-1.5">
                <Smartphone className="w-3.5 h-3.5 text-emerald-400" />
                <span>允许 Web Push 浏览器与移动端推送通知 (支持切后台通知)</span>
              </span>
            </label>

            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={notifySystem}
                onChange={(e) => setNotifySystem(e.target.checked)}
                className="rounded border-slate-700 text-emerald-600 focus:ring-0"
              />
              <span className="text-slate-200 flex items-center space-x-1.5">
                <Bell className="w-3.5 h-3.5 text-sky-400" />
                <span>系统原生桌面通知</span>
              </span>
            </label>
          </div>

          {/* 底部按钮 */}
          <footer className="pt-3 border-t border-slate-800 flex items-center justify-end space-x-2">
            <button
              type="button"
              onClick={closeDispatchModal}
              className="px-3.5 py-1.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              aria-label="发完走人立即派发"
              className="px-4 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-md shadow flex items-center space-x-1.5 transition-all"
            >
              <Send className="w-3.5 h-3.5" />
              <span>发完走人 · 立即派发</span>
            </button>
          </footer>
        </form>
      </dialog>
    </>
  );
};
