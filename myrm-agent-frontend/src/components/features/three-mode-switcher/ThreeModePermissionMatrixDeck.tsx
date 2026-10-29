import React from 'react';
import {
  ShieldCheck,
  X,
  Check,
  Minus,
  MessageSquare,
  FileText,
  Sparkles,
} from 'lucide-react';
import { useThreeModeStore } from './useThreeModeStore';
import { OFFICE_MODES } from './threeModeEngine';
import { OfficeWorkspaceMode } from './threeModeTypes';

export const ThreeModePermissionMatrixDeck: React.FC = () => {
  const { isMatrixOpen, closeMatrix, currentMode, setMode } = useThreeModeStore();

  if (!isMatrixOpen) {
    return null;
  }

  const modeKeys: OfficeWorkspaceMode[] = ['ask', 'plan', 'craft'];

  const getModeIcon = (mode: OfficeWorkspaceMode) => {
    switch (mode) {
      case 'ask':
        return <MessageSquare className="w-4 h-4 text-emerald-400" />;
      case 'plan':
        return <FileText className="w-4 h-4 text-indigo-400" />;
      case 'craft':
        return <Sparkles className="w-4 h-4 text-amber-400" />;
    }
  };

  return (
    <div
      data-testid="three-mode-permission-matrix-deck"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm select-none"
    >
      <dialog
        open
        aria-modal="true"
        aria-labelledby="matrix-deck-title"
        className="w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col gap-5 text-slate-200"
      >
        {/* 顶部标题与关闭 */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h2 id="matrix-deck-title" className="text-sm font-bold text-white">
                三态心智模式安全说明
              </h2>
              <p className="text-[11px] text-slate-400">
                将技术权限降维为通俗的工作习惯，为办公文件保驾护航
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={closeMatrix}
            className="p-1.5 rounded-xl hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="关闭说明"
            aria-label="关闭说明"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 三列模式卡片对比 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {modeKeys.map((key) => {
            const meta = OFFICE_MODES[key];
            const isCurrent = currentMode === key;

            return (
              <div
                key={key}
                className={`p-3.5 rounded-2xl border flex flex-col justify-between transition-all ${
                  isCurrent
                    ? 'bg-indigo-950/40 border-indigo-500 shadow-md ring-1 ring-indigo-500/50'
                    : 'bg-slate-950/50 border-slate-800'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5 font-bold text-xs text-white">
                      {getModeIcon(key)}
                      <span>{meta.title}</span>
                    </div>
                    {isCurrent && (
                      <span className="px-1.5 py-0.2 rounded text-[9px] font-mono bg-indigo-600 text-white font-semibold">
                        当前
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-slate-400 leading-snug mb-3">
                    {meta.description}
                  </p>

                  {/* 权限清单 */}
                  <div className="space-y-1.5 pt-2 border-t border-slate-800 text-[11px]">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">修改本地文件</span>
                      {meta.policy.allowFileWrites ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Minus className="w-3.5 h-3.5 text-slate-600" />
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">执行命令行脚本</span>
                      {meta.policy.allowShellExecution ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Minus className="w-3.5 h-3.5 text-slate-600" />
                      )}
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">强制先出计划</span>
                      {meta.policy.requirePlanApproval ? (
                        <Check className="w-3.5 h-3.5 text-indigo-400" />
                      ) : (
                        <Minus className="w-3.5 h-3.5 text-slate-600" />
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-2 border-t border-slate-800/80">
                  <span className="text-[10px] text-slate-500 block mb-2 leading-tight">
                    适合：{meta.recommendedFor}
                  </span>

                  {!isCurrent && (
                    <button
                      type="button"
                      onClick={() => {
                        setMode(key);
                        closeMatrix();
                      }}
                      className="w-full py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-[11px] transition-colors"
                    >
                      切换到此模式
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部小贴士 */}
        <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-500 font-mono flex items-center justify-between">
          <span>无需重启会话，对话中随时无缝换挡</span>
          <span className="text-indigo-400 font-semibold">100% 本地安全保护</span>
        </div>
      </dialog>
    </div>
  );
};
